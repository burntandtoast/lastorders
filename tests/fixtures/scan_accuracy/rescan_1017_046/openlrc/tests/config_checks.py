import unittest


class TestModelConfig(unittest.TestCase):
    def test_model_config_str(self):
        mc = ModelConfig(provider=ModelProvider.OPENAI, name="gpt-4")
        self.assertEqual(str(mc), "openai:gpt-4")
