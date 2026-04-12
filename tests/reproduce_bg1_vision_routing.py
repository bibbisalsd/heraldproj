import unittest
from unittest.mock import MagicMock, patch
import os

# Mocking necessary components before imports if needed, 
# but better to use patch in tests.

from jarvis.brain_core.prompt_dispatcher import PromptDispatcher, TaskDecision
from jarvis.brain_core.task_classifier import TaskClassifier
from jarvis.brain_core.bg1_manager import BG1Manager
from jarvis.config import JarvisConfig

class TestReproduceBugs(unittest.TestCase):
    def setUp(self):
        self.config = JarvisConfig()
        self.mock_runtime = MagicMock()
        self.mock_runtime.config = self.config
        
        # Mocking bg1_queue and job_status for BG1Manager
        self.mock_runtime.bg1_queue.active.job_id = "test_job_1"
        self.mock_runtime.job_status.get_current.return_value = MagicMock(job_id="test_job_1", cancel_requested=False, force_kill_requested=False)

    def test_bug_1_bg1_logic_specialist_routing_and_swallow(self):
        """
        1) BG1 manager silent swallow and missing Logic Specialist (deepseek-r1:8b) routing.
        Demonstrates that BG1Manager uses logic_specialist_model and swallows errors.
        """
        bg1 = BG1Manager(self.mock_runtime)
        
        # Mock OllamaClient to simulate failure
        with patch('jarvis.brain_core.bg1_manager.OllamaClient') as MockClient:
            mock_client_instance = MockClient.return_value
            mock_client_instance.chat.return_value = MagicMock(ok=False, error="Ollama connection failed")
            
            # A task that doesn't trigger vision, code, or URL
            summary = "Tell me about the history of quantum computing in great detail."
            
            # We need to mock _build_bg1_context_prefix to avoid more mocks
            bg1._build_bg1_context_prefix = MagicMock(return_value="")
            
            # We'll check if it logs the error. 
            # Currently it doesn't, so we expect this to fail if we assert it does.
            with self.assertLogs('jarvis.brain_core.bg1_manager', level='ERROR') as cm:
                result = bg1._execute_bg1_specialist(summary)
                
                # Verify it used the logic specialist model
                MockClient.assert_called_with(
                    model=self.config.logic_specialist_model,
                    timeout_seconds=300
                )
                
                # If it swallows silently, result is generic and no log is emitted.
                # We want it to NOT swallow silently.
                self.assertIn("Ollama connection failed", cm.output[0])

    def test_bug_2_vision_model_mapping_conflict(self):
        """
        2) Vision model mapping conflicts in config.py (gemma4 vs qwen3).
        Demonstrates that JarvisRuntime uses the wrong vision model in realtime lane.
        """
        from jarvis.main import JarvisRuntime
        with patch('jarvis.main.build_default_config', return_value=self.config):
            with patch('jarvis.main.PersistentEventLogger'):
                with patch('jarvis.main.Memory'):
                    with patch('jarvis.main.IngressHub'):
                        with patch('jarvis.main.TTS'):
                            runtime = JarvisRuntime()
                            runtime._capabilities_for_profile = MagicMock(return_value={})
                            
                            env = MagicMock()
                            env.text = "What is in this image?"
                            decision = MagicMock()
                            decision.intent = "screen_query"
                            
                            runtime.intent_registry.resolve = MagicMock(return_value=None)
                            runtime.conversation.handle_memory_wipe_flow = MagicMock(return_value=None)
                            runtime.conversation.handle_creator_verification_flow = MagicMock(return_value=None)
                            runtime.conversation.handle_title_clarification_flow = MagicMock(return_value=None)
                            runtime.conversation.handle_owner_onboarding = MagicMock(return_value=None)
                            runtime.conversation.handle_creator_claim = MagicMock(return_value=None)
                            runtime.conversation.handle_creator_context = MagicMock(return_value=None)
                            runtime.turn_pipeline._generate_general_chat_reply = MagicMock(return_value=None)
                            
                            runtime._execute_realtime(env, decision)
                            
                            args, kwargs = runtime.intent_registry.resolve.call_args
                            services = args[2]
                            
                            vision_specialist_lambda = services["run_vision_specialist"]
                            
                            with patch('jarvis.main.run_specialist_vision') as mock_run_vision:
                                vision_specialist_lambda("test task")
                                # This should fail because current code uses vision_bg1_model
                                mock_run_vision.assert_called_with("test task", model=self.config.vision_lite_model)

    def test_bug_3_task_classifier_long_chat_routing(self):
        """
        3) Intent Routing Stage 5 TaskClassifier failing on general chat (word count > 25, no keywords).
        Demonstrates that long general chat is incorrectly routed to BG1.
        """
        classifier = TaskClassifier()
        
        # A long general chat message (> 25 words)
        long_chat = (
            "I was thinking about how beautiful the weather is today and I wanted to tell you "
            "a very long story about my childhood when I used to go to the park every single day "
            "with my grandfather and we would feed the ducks and eat ice cream together under the big oak tree."
        )
        
        decision = classifier.classify(long_chat)
        
        # Correct behavior: should be realtime
        # Current code: routes to bg1 if > 25 words
        self.assertEqual(decision.lane, "realtime", f"Long chat should be realtime, but got {decision.lane}")

if __name__ == "__main__":
    unittest.main()
