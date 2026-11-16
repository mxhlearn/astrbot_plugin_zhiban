"""Accounting wrappers must retain the provider contract used by modules."""
import ast
from pathlib import Path
import unittest


class UsageProviderTypeTests(unittest.TestCase):
    def test_provider_identity_and_accounting_are_preserved(self):
        source = Path(__file__).parents[1] / "astrbot_plugin_zhiban/runtime.py"
        tree = ast.parse(source.read_text(encoding="utf-8"))
        proxy_node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_UsageProviderProxy")
        namespace = {}
        exec(compile(ast.Module(body=[proxy_node], type_ignores=[]), str(source), "exec"), namespace)

        class Provider:
            async def text_chat(self, **kwargs):
                return {"usage": {"total_tokens": 3}}

        class ChatProvider(Provider):
            provider_config = {"model": "fixture"}

        class Usage:
            def __init__(self):
                self.records = []

            def record_response(self, response, **kwargs):
                self.records.append((response, kwargs))

        import asyncio
        usage = Usage()
        proxy = namespace["_UsageProviderProxy"](ChatProvider(), usage, "memory")
        self.assertIsInstance(proxy, Provider)
        self.assertIsInstance(proxy, ChatProvider)
        self.assertIsInstance(proxy, namespace["_UsageProviderProxy"])
        self.assertEqual(proxy.provider_config["model"], "fixture")
        self.assertEqual(asyncio.run(proxy.text_chat())["usage"]["total_tokens"], 3)
        self.assertEqual(len(usage.records), 1)


if __name__ == "__main__":
    unittest.main()
