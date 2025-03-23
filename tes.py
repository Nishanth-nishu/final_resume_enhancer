import unittest
from unittest.mock import patch, MagicMock
from app import app, enhance_resume_with_gemini, extract_resume_text, generate_pdf
import os
import tempfile
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter

class TestGeminiIntegration(unittest.TestCase):
    def setUp(self):
        self.app_context = app.app_context()
        self.app_context.push()
        self.client = app.test_client()
        self.test_resume_text = "Test Resume Content"
        self.test_job_description = "Test Job Description"
        self.test_template_type = "engineering"
        self.test_enhanced_resume = "Enhanced Test Resume Content"

    def tearDown(self):
        self.app_context.pop()

    @patch('google.generativeai.GenerativeModel')
    def test_enhance_resume_with_gemini_success(self, mock_generative_model):
        mock_response = MagicMock()
        mock_response.text = self.test_enhanced_resume
        mock_generative_model.return_value.generate_content.return_value = mock_response

        enhanced_resume = enhance_resume_with_gemini(
            self.test_resume_text, self.test_job_description, self.test_template_type
        )

        self.assertEqual(enhanced_resume, self.test_enhanced_resume)
        mock_generative_model.return_value.generate_content.assert_called_once()

    @patch('google.generativeai.GenerativeModel')
    def test_enhance_resume_with_gemini_empty_response(self, mock_generative_model):
        mock_response = MagicMock()
        mock_response.text = ""
        mock_generative_model.return_value.generate_content.return_value = mock_response

        with self.assertRaises(ValueError) as context:
            enhance_resume_with_gemini(
                self.test_resume_text, self.test_job_description, self.test_template_type
            )
        self.assertIn("Gemini API returned an empty response", str(context.exception))

    @patch('google.generativeai.GenerativeModel')
    def test_enhance_resume_with_gemini_api_error(self, mock_generative_model):
        mock_generative_model.return_value.generate_content.side_effect = Exception("API Error")

        with self.assertRaises(ValueError) as context:
            enhance_resume_with_gemini(
                self.test_resume_text, self.test_job_description, self.test_template_type
            )
        self.assertIn("Error communicating with Gemini API", str(context.exception))

    def test_extract_resume_text_pdf(self):
        # Create a simple PDF using reportlab
        c = canvas.Canvas("test.pdf", pagesize=letter)
        c.drawString(100, 750, "Test PDF Content")
        c.save()

        extracted_text = extract_resume_text("test.pdf")
        self.assertIn("Test PDF Content", extracted_text)
        os.remove("test.pdf")

    # ... (rest of your tests remain the same) ...

if __name__ == "__main__":
    unittest.main()
