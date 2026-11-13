"""Run with Python unittest; no AstrBot process, credentials or network needed."""
from __future__ import annotations
import ast
import asyncio
import base64
import importlib.util
import io
import gzip
import logging
import sys
import tempfile
import time
import types
import unittest
import uuid
from collections import OrderedDict
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from PIL import Image

MODULES = Path(__file__).resolve().parents[1] / 'astrbot_plugin_zhiban' / 'modules'


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def package(name, path):
    module = types.ModuleType(name)
    module.__path__ = [str(path)]
    sys.modules[name] = module


def extract_class(path, name, globals_, methods=None):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    if methods:
        cls.bases = []
        cls.decorator_list = []
        cls.body = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name in methods]
        for method in cls.body:
            method.decorator_list = []
    unit = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0), cls], type_ignores=[])
    exec(compile(ast.fix_missing_locations(unit), str(path), 'exec'), globals_)
    return globals_[name]


class MediaRegressionTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.saved = dict(sys.modules)
        api = types.ModuleType('astrbot.api'); api.logger = logging.getLogger('test')
        star_tools = types.ModuleType('astrbot.core.star.star_tools')
        star_tools.StarTools = types.SimpleNamespace(get_data_dir=lambda _name: Path(cls.temp.name))
        cls.module_patch = patch.dict(sys.modules, {'astrbot.api': api, 'astrbot.core.star.star_tools': star_tools})
        cls.module_patch.start()
        brush = MODULES / 'astrbot_plugin_angel_brush'
        package('_media_brush', brush); package('_media_brush.core', brush/'core')
        cls.storage = load_file('_media_brush.core.storage', brush/'core/storage.py')
        cls.service = load_file('_media_brush.core.service', brush/'core/service.py')
        eye = MODULES/'astrbot_plugin_angel_eye'
        package('_media_eye', eye); package('_media_eye.services', eye/'services'); package('_media_eye.core', eye/'core')
        formatter = types.ModuleType('_media_eye.core.formatter'); formatter.format_unified_message=lambda msg, _id: str(msg)
        sys.modules[formatter.__name__]=formatter
        cls.repo_module = load_file('_media_eye.services.history_repository', eye/'services/history_repository.py')
        cls.history = load_file('_media_eye.services.qq_history_service', eye/'services/qq_history_service.py')
        cls.FeedCache = extract_class(MODULES/'astrbot_plugin_qzone_ultra/qzone_bridge/client.py','FeedCache',{'OrderedDict':OrderedDict,'time':time})
        cls.Breeze = extract_class(MODULES/'astrbot_plugin_breeze_tts/main.py','BreezeTTSPlugin',{'Path':Path,'time':time,'uuid':uuid,'logger':logging.getLogger('test')}, {'synthesize','decorate_reply'})

    @classmethod
    def tearDownClass(cls):
        cls.module_patch.stop()
        for key in list(sys.modules):
            if key.startswith(('_media_brush','_media_eye')) and key not in cls.saved:
                sys.modules.pop(key,None)
        cls.temp.cleanup()

    async def test_brush_bounded_chunked_response(self):
        class Chunks(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b'a'*100
                yield b'b'*100
        async def handler(req):
            return httpx.Response(200,stream=Chunks())
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError, '超过'):
                await self.service._bounded_request(client,'GET','https://example.test/image',max_bytes=150)

    async def test_brush_declared_length_rejected(self):
        async def handler(req):
            return httpx.Response(200,headers={'content-length':'999'},content=b'x')
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(ValueError):
                await self.service._bounded_request(client,'GET','https://example.test/image',max_bytes=100)

    async def test_brush_success_and_http_error_body_bound(self):
        async def handler(req): return httpx.Response(200,json={'data':[{'url':'https://example.test/a'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response=await self.service._bounded_request(client,'POST','https://example.test/generate',json={'prompt':'cat'})
            self.assertEqual(response.json()['data'][0]['url'],'https://example.test/a')

    async def test_brush_compressed_response_decoded_once(self):
        encoded = gzip.compress(b'{"data": []}')
        async def handler(req):
            return httpx.Response(200, headers={"content-encoding": "gzip"}, content=encoded)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            response = await self.service._bounded_request(client, 'POST', 'https://example.test/generate')
            self.assertEqual(response.json(), {"data": []})
            self.assertNotIn('content-encoding', response.headers)

    async def test_brush_edit_count_and_total_including_mask(self):
        with self.assertRaises(ValueError):
            await self.service._load_edit_inputs({'operation':'edit','images':['x']*5,'mask':None})
        payload=b'x'*(8*1024*1024)
        with patch.object(self.service,'_load_image_bytes',AsyncMock(return_value=(payload,'image/png'))), patch.object(self.storage,'format_info'):
            with self.assertRaisesRegex(ValueError,'总量'):
                await self.service._load_edit_inputs({'operation':'edit','images':['a','b','c'],'mask':'d'})

    async def test_local_image_limit_and_real_png(self):
        image=io.BytesIO(); Image.new('RGB',(2,2)).save(image,format='PNG')
        self.assertEqual(self.storage.format_info(image.getvalue())[2:],(2,2))
        path=Path(self.temp.name)/'large.png'
        with path.open('wb') as f: f.truncate(self.storage.MAX_IMAGE_BYTES+1)
        with self.assertRaises(ValueError): self.service._read_local_image(path)
        with patch.object(self.storage,'MAX_PIXELS',1):
            with self.assertRaisesRegex(ValueError,'尺寸'): self.storage.format_info(image.getvalue())

    async def test_tts_bounded_audio_and_non_stream_endpoint(self):
        class Content:
            async def iter_chunked(self,size):
                yield b'x'*(4*1024*1024)
                yield b'x'*(4*1024*1024+1)
        class Response:
            status=200; content_length=None; content=Content()
            async def __aenter__(self): return self
            async def __aexit__(self,*_): pass
        urls=[]
        def post(url, **kwargs):
            urls.append(url)
            return Response()
        session=types.SimpleNamespace(post=post)
        obj=self.Breeze(); obj._cfg=lambda key,default=None: {'api_key':'test','voice_id':'test'}.get(key,default)
        obj._base=lambda:'https://example.test'; obj._ensure_session=AsyncMock(return_value=session)
        obj.temp_dir=Path(self.temp.name); obj._cleanup=lambda:None
        with self.assertRaisesRegex(RuntimeError,'8 MiB'): await obj.synthesize('hello')
        self.assertEqual(list(obj.temp_dir.glob('*.wav')),[])
        self.assertEqual(urls, ['https://example.test/v1/text-to-speech/test?output_format=wav'])

    async def test_tts_skips_command_result(self):
        obj=self.Breeze(); obj._allowed_here=lambda event:True
        result=types.SimpleNamespace(is_llm_result=lambda:False)
        event=types.SimpleNamespace(get_result=lambda:result)
        await obj.decorate_reply(event)

    async def test_qzone_cache_lru_and_expiry(self):
        now=[1.0]; cache=self.FeedCache(max_items=2,ttl=10,clock=lambda:now[0])
        cache['a']=1; cache['b']=2; self.assertEqual(cache.get('a'),1)
        cache['c']=3; self.assertIsNone(cache.get('b')); self.assertEqual(len(cache),2)
        now[0]=12; self.assertIsNone(cache.get('a')); self.assertEqual(len(cache),0)
        cache['x']=1; cache.clear(); self.assertEqual(cache._expires,{})

    async def test_history_modern_signed_anchor_and_order(self):
        service=self.history.QQChatHistoryService({'history_api_mode':'snowluma_v24'},Path(self.temp.name)/'modern.db')
        try:
            call=AsyncMock(return_value={'messages':[{'message_id':42,'message_seq':99,'time':20},{'message_id':-123,'message_seq':88,'time':10}]})
            messages=await service._fetch_page(types.SimpleNamespace(api=types.SimpleNamespace(call_action=call)),'55',-9)
            call.assert_awaited_once_with('get_group_msg_history',group_id=55,message_id=-9,count=50,reverse_order=True)
            service.repo.insert_messages('55',messages)
            self.assertEqual(service.repo.rebuild_oldest_seq_from_messages('55'),-123)
            self.assertEqual(service.repo.extract_anchor(messages[0],'snowluma_v24'),-123)
            self.assertIsNone(service.repo.extract_anchor({'message_seq':88},'snowluma_v24'))
        finally: service.close()

    async def test_history_legacy_payload_unchanged(self):
        service=self.history.QQChatHistoryService({},Path(self.temp.name)/'legacy.db')
        try:
            call=AsyncMock(return_value={'messages':[]})
            await service._fetch_page(types.SimpleNamespace(api=types.SimpleNamespace(call_action=call)),'55',7)
            call.assert_awaited_once_with('get_group_msg_history',group_id=55,message_seq=7,reverseOrder=True)
        finally: service.close()

    async def test_history_loop_page_limit_and_signed_state(self):
        service=self.history.QQChatHistoryService({'history_api_mode':'snowluma_v24','max_pages':2},Path(self.temp.name)/'loop.db')
        service.config.server_call_delay=0
        try:
            pages=[[{'message_id':-999,'message_seq':9,'time':200}],[{'message_id':222,'message_seq':8,'time':100}]]
            service._fetch_page=AsyncMock(side_effect=pages)
            result=await service._head_fill(None,'55',service.repo.get_sync_state('55'),1)
            self.assertEqual(result.stop_reason,'page_limit');self.assertEqual(result.pages_fetched,2)
            service.repo.upsert_sync_state('55',oldest_seq=-999,covered_from=200)
            service.repo.upsert_sync_state('55',oldest_seq=222,covered_from=100)
            self.assertEqual(service.repo.get_sync_state('55').oldest_seq,222)
        finally: service.close()

    async def test_history_page_timeout(self):
        service=self.history.QQChatHistoryService({},Path(self.temp.name)/'timeout.db')
        service.config.page_timeout=.01
        async def slow(*args,**kwargs): await asyncio.sleep(.1)
        try:
            with self.assertRaises(asyncio.TimeoutError):
                await service._fetch_page(types.SimpleNamespace(api=types.SimpleNamespace(call_action=slow)),'1',0)
        finally: service.close()

    async def test_history_cache_expiry_and_oversize_message(self):
        service=self.history.QQChatHistoryService({},Path(self.temp.name)/'prune.db')
        try:
            oversized={'message_id':1,'time':100,'message':[{'type':'text','data':{'text':'x'*17000}}]}
            result=service.repo.insert_messages('55',[oversized])
            self.assertEqual(result.inserted_count,0)
            service.repo.insert_messages('55',[{'message_id':2,'time':100}])
            service.repo._conn.execute('UPDATE messages SET created_at=?',(int(time.time())-8*86400,))
            service.repo._conn.commit()
            service.repo.prune_cache()
            self.assertEqual(service.repo.count_messages('55'),0)
        finally: service.close()

    async def test_history_repeated_page_stops(self):
        service=self.history.QQChatHistoryService({'history_api_mode':'snowluma_v24'},Path(self.temp.name)/'repeat.db')
        service.config.server_call_delay=0
        try:
            service._fetch_page=AsyncMock(return_value=[{'message_id':-7,'time':100}])
            result=await service._head_fill(None,'55',service.repo.get_sync_state('55'),1)
            self.assertLessEqual(result.pages_fetched,2)
        finally: service.close()


if __name__=='__main__': unittest.main(verbosity=2)
