from flask import Flask, request, jsonify, render_template, send_file, url_for
import os
import google.generativeai as genai
from dotenv import load_dotenv
import logging
import tempfile
from werkzeug.utils import secure_filename
import uuid
import json
import re
from datetime import datetime
import html
import requests
import io
from PIL import Image, ImageDraw, ImageFont
import textwrap
import base64
import time
import asyncio
import hashlib
from typing import Dict, List, Tuple, Optional, Any, Union

# For PDF generation with better Unicode support
from fpdf import FPDF

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("app.log"),  # Log to a file
        logging.StreamHandler()  # Log to console
    ]
)

app = Flask(__name__, static_folder='static')

# Configure Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY environment variable not set!")
    raise ValueError("GEMINI_API_KEY not configured")

# Initialize Gemini 1.5
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")  # Use Pro model for better quality

# Ensure necessary directories exist
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "enhanced_resumes"
TEMPLATE_FOLDER = "templates"
FONTS_FOLDER = "fonts"

for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, TEMPLATE_FOLDER, FONTS_FOLDER, 
               os.path.join("static", "js"), os.path.join("static", "css")]:
    os.makedirs(folder, exist_ok=True)

# File configuration
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt', 'rtf'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Download and save free fonts if they don't exist
FONT_URLS = {
    "OpenSans-Regular": "https://github.com/google/fonts/raw/main/apache/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf",
    "OpenSans-Bold": "https://github.com/google/fonts/raw/main/apache/opensans/OpenSans%5Bwdth%2Cwght%5D.ttf",
    "Roboto-Regular": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf",
    "Roboto-Bold": "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
}

def download_fonts():
    """Download free fonts for PDF generation if they don't exist."""
    for font_name, url in FONT_URLS.items():
        font_path = os.path.join(FONTS_FOLDER, f"{font_name}.ttf")
        if not os.path.exists(font_path):
            try:
                logging.info(f"Downloading font: {font_name}")
                response = requests.get(url)
                response.raise_for_status()
                with open(font_path, 'wb') as f:
                    f.write(response.content)
                logging.info(f"Font downloaded: {font_name}")
            except Exception as e:
                logging.error(f"Error downloading font {font_name}: {e}")

# Call this at startup
download_fonts()

def allowed_file(filename):
    """Check if the file extension is allowed."""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    """Render the frontend HTML."""
    return render_template("index.html")

@app.route("/api/enhance-resume", methods=["POST"])
def enhance_resume():
    """API endpoint to enhance a resume."""
    try:
        logging.info("Enhance resume request received")

        # Get uploaded file and job description
        if 'resume' not in request.files:
            logging.error("No resume file uploaded")
            return jsonify({"error": "No resume file uploaded"}), 400
            
        resume_file = request.files['resume']
        logging.info(f"Resume file: {resume_file.filename}")
        
        if resume_file.filename == '':
            logging.error("No file selected")
            return jsonify({"error": "No file selected"}), 400
            
        if not allowed_file(resume_file.filename):
            logging.error(f"Invalid file type: {resume_file.filename}")
            return jsonify({"error": f"Only {', '.join(ALLOWED_EXTENSIONS)} files are allowed"}), 400
            
        # Check file size
        resume_file.seek(0, os.SEEK_END)
        file_size = resume_file.tell()
        resume_file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            logging.error(f"File size exceeds limit: {file_size} bytes")
            return jsonify({"error": "File size exceeds 10MB limit"}), 400
            
        job_description = request.form.get("jobDescription", "")
        template_type = request.form.get("template", "engineering")
        output_format = request.form.get("outputFormat", "standard")  # New parameter for output format
        
        if not job_description:
            logging.error("Job description is required")
            return jsonify({"error": "Job description is required"}), 400

        # Create a unique filename
        filename = secure_filename(resume_file.filename)
        unique_id = str(uuid.uuid4())
        file_extension = os.path.splitext(filename)[1]
        secure_filename_with_id = f"{unique_id}{file_extension}"
        file_path = os.path.join(UPLOAD_FOLDER, secure_filename_with_id)
        
        # Save the uploaded file
        resume_file.save(file_path)
        logging.info(f"File saved to: {file_path}")
        
        # Extract text from the resume
        try:
            resume_text = extract_resume_text(file_path)
            logging.info("Resume text extracted successfully")
        except Exception as e:
            logging.error(f"Error extracting text: {e}")
            os.remove(file_path)  # Clean up the file
            return jsonify({"error": f"Could not extract text from file: {str(e)}"}), 400
            
        # Enhance resume using Gemini API with appropriate template
        try:
            enhanced_resume, skills_list, keywords_used = enhance_resume_with_gemini(
                resume_text, job_description, template_type
            )
            logging.info("Resume enhanced successfully")
        except Exception as e:
            logging.error(f"Error enhancing resume: {e}")
            return jsonify({"error": f"Failed to enhance resume: {str(e)}"}), 500
        
        # Generate PDF of the enhanced resume with the selected template
        pdf_filename = f"enhanced_resume_{unique_id}.pdf"
        pdf_path = os.path.join(OUTPUT_FOLDER, pdf_filename)
        
        try:
            generate_pdf(enhanced_resume, pdf_path, template_type, skills_list, output_format)
            logging.info(f"PDF generated: {pdf_path}")
        except Exception as e:
            logging.error(f"Error generating PDF: {e}")
            return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500

        # Generate a text version for download
        txt_filename = f"enhanced_resume_{unique_id}.txt"
        txt_path = os.path.join(OUTPUT_FOLDER, txt_filename)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(enhanced_resume)

        # Generate a match score between resume and job description
        match_score = calculate_match_score(enhanced_resume, job_description)

        return jsonify({
            "originalResume": resume_text,
            "enhancedResume": enhanced_resume,
            "pdfUrl": url_for('download_resume', filename=pdf_filename, type='pdf'),
            "txtUrl": url_for('download_resume', filename=txt_filename, type='txt'),
            "matchScore": match_score,
            "keywordsUsed": keywords_used,
            "skills": skills_list
        })
        
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route("/download/<filename>/<type>")
def download_resume(filename, type):
    """Route to download generated resume files."""
    try:
        if type not in ['pdf', 'txt']:
            return "Invalid file type", 400
            
        # Verify the filename is safe
        safe_filename = secure_filename(filename)
        if safe_filename != filename:
            return "Invalid filename", 400
            
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        
        # Check if file exists
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return "File not found", 404
            
        # Set the appropriate MIME type
        mime_type = "application/pdf" if type == 'pdf' else "text/plain"
        
        # Set a more user-friendly download filename
        download_name = f"Resume.{type}"
        
        return send_file(
            file_path,
            mimetype=mime_type,
            as_attachment=True,
            download_name=download_name
        )
        
    except Exception as e:
        logging.error(f"Error downloading file: {e}")
        return "Error downloading file", 500

def extract_resume_text(file_path: str) -> str:
    """Extract text from a resume file (PDF, DOCX, TXT, or RTF)."""
    try:
        if file_path.endswith(".pdf"):
            try:
                # Try using PyPDF2 first (simpler dependency)
                from PyPDF2 import PdfReader
                reader = PdfReader(file_path)
                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n"
                
                if text.strip():
                    return text
                    
                # If PyPDF2 fails to extract meaningful text, try pdfminer
                logging.info("PyPDF2 extraction was empty, trying pdfminer...")
            except Exception as e:
                logging.warning(f"PyPDF2 extraction failed: {e}, trying pdfminer...")
                
            # Fallback to pdfminer for better text extraction
            from pdfminer.high_level import extract_text as pdfminer_extract
            text = pdfminer_extract(file_path)
            return text if text.strip() else "No text could be extracted from PDF"
            
        elif file_path.endswith(".docx"):
            try:
                from docx import Document
                doc = Document(file_path)
                return "\n".join([para.text for para in doc.paragraphs])
            except Exception as e:
                logging.error(f"Error extracting DOCX: {e}")
                # Try alternative extraction
                import subprocess
                try:
                    # Use pandoc if available
                    result = subprocess.run(
                        ["pandoc", "-f", "docx", "-t", "plain", file_path],
                        capture_output=True, text=True, check=True
                    )
                    return result.stdout
                except Exception as e2:
                    logging.error(f"Alternative DOCX extraction failed: {e2}")
                    raise
            
        elif file_path.endswith(".rtf"):
            try:
                # First try using striprtf
                from striprtf.striprtf import rtf_to_text
                with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                    rtf_text = f.read()
                return rtf_to_text(rtf_text)
            except Exception as e:
                logging.warning(f"striprtf failed: {e}, trying alternative...")
                # Try using pandoc as fallback
                import subprocess
                try:
                    result = subprocess.run(
                        ["pandoc", "-f", "rtf", "-t", "plain", file_path],
                        capture_output=True, text=True, check=True
                    )
                    return result.stdout
                except Exception as e2:
                    logging.error(f"Alternative RTF extraction failed: {e2}")
                    raise
            
        elif file_path.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
    except Exception as e:
        logging.error(f"Error in extract_resume_text: {e}")
        raise

def enhance_resume_with_gemini(resume_text: str, job_description: str, template_type: str) -> tuple:
    """Enhance the resume text using Gemini API with appropriate template."""
    try:
        # Select prompt template based on template_type
        if template_type == "faang":
            prompt_template = """
            You are an expert resume editor for FAANG companies (Facebook, Amazon, Apple, Netflix, Google).
            
            Please enhance the following resume to target the job description provided. 
            
            Focus on:
            1. Using quantifiable achievements and metrics (add realistic metrics if missing)
            2. Highlighting technical skills and projects relevant to the job
            3. Using action verbs and demonstrating impact
            4. Removing irrelevant information
            5. Organizing content for maximum readability
            6. Using STAR methodology (Situation, Task, Action, Result) for experiences
            7. Making sure the resume is ATS-friendly (Applicant Tracking System)
            8. Adding relevant keywords from the job description
            9. Improving the professional summary for maximum impact
            
            Resume to enhance:
            ```
            {resume_text}
            ```
            
            Job Description:
            ```
            {job_description}
            ```
            
            First, identify the key skills and keywords in the job description. Then, enhance the resume to highlight these skills.
            
            Your output must be in this JSON format:
            {{
                "enhanced_resume": "The complete enhanced resume as plain text with professional formatting",
                "skills_list": ["Skill 1", "Skill 2", "Skill 3"...],  // List of 5-10 most important skills from the resume
                "keywords_used": ["Keyword 1", "Keyword 2", "Keyword 3"...]  // List of keywords from job description used in the resume
            }}
            
            Ensure the enhanced resume maintains professional formatting in plain text.
            """
        elif template_type == "non-tech":
            prompt_template = """
            You are an expert resume editor for non-technical professionals.
            
            Please enhance the following resume to target the job description provided.
            
            Focus on:
            1. Highlighting transferable skills and relevant accomplishments
            2. Using industry-specific terminology from the job description
            3. Emphasizing soft skills and interpersonal abilities
            4. Quantifying achievements whenever possible (add realistic metrics if missing)
            5. Ensuring clear organization and professional formatting
            6. Tailoring the professional summary to match the job requirements
            7. Making sure the resume is ATS-friendly (Applicant Tracking System)
            8. Using action verbs that demonstrate leadership and initiative
            9. Highlighting relevant certifications or training
            
            Resume to enhance:
            ```
            {resume_text}
            ```
            
            Job Description:
            ```
            {job_description}
            ```
            
            First, identify the key skills and keywords in the job description. Then, enhance the resume to highlight these skills.
            
            Your output must be in this JSON format:
            {{
                "enhanced_resume": "The complete enhanced resume as plain text with professional formatting",
                "skills_list": ["Skill 1", "Skill 2", "Skill 3"...],  // List of 5-10 most important skills from the resume
                "keywords_used": ["Keyword 1", "Keyword 2", "Keyword 3"...]  // List of keywords from job description used in the resume
            }}
            
            Ensure the enhanced resume maintains professional formatting in plain text.
            """
        else:  # Default to engineering template
            prompt_template = """
            You are an expert resume editor for engineering professionals.
            
            Please enhance the following resume to target the job description provided.
            
            Focus on:
            1. Highlighting relevant technical skills and engineering achievements
            2. Using proper engineering terminology aligned with the job description
            3. Emphasizing problem-solving abilities and technical solutions
            4. Quantifying results and impact where possible (add realistic metrics if missing)
            5. Organizing content for maximum readability
            6. Including relevant projects, technologies, and methodologies
            7. Making sure the resume is ATS-friendly (Applicant Tracking System)
            8. Adding relevant keywords from the job description
            9. Creating a compelling professional summary
            
            Resume to enhance:
            ```
            {resume_text}
            ```
            
            Job Description:
            ```
            {job_description}
            ```
            
            First, identify the key skills and keywords in the job description. Then, enhance the resume to highlight these skills.
            
            Your output must be in this JSON format:
            {{
                "enhanced_resume": "The complete enhanced resume as plain text with professional formatting",
                "skills_list": ["Skill 1", "Skill 2", "Skill 3"...],  // List of 5-10 most important skills from the resume
                "keywords_used": ["Keyword 1", "Keyword 2", "Keyword 3"...]  // List of keywords from job description used in the resume
            }}
            
            Ensure the enhanced resume maintains professional formatting in plain text.
            """
        
        # Format the prompt with the actual resume and job description
        formatted_prompt = prompt_template.format(
            resume_text=resume_text,
            job_description=job_description
        )
        
        # Use Gemini Pro to generate the enhanced resume
        response = model.generate_content(
            contents=formatted_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,  # Lower temperature for more consistent results
                max_output_tokens=4000,  # Higher token limit for longer resumes
                response_mime_type="application/json"  # Request JSON response
            )
        )
        
        # Check if we have a valid response
        if not response.text:
            logging.error("Empty or invalid response from Gemini API")
            return "Error: Could not generate enhanced resume. Please try again.", [], []
        
        # Parse the JSON response
        try:
            result = json.loads(response.text)
            enhanced_resume = result.get("enhanced_resume", "")
            skills_list = result.get("skills_list", [])
            keywords_used = result.get("keywords_used", [])
            
            # Clean the enhanced resume text
            enhanced_resume = enhanced_resume.strip()
            
            # Remove any markdown code blocks if present
            enhanced_resume = re.sub(r'```[a-z]*\n', '', enhanced_resume)
            enhanced_resume = enhanced_resume.replace('```', '')
            
            # Remove all markdown formatting
            enhanced_resume = re.sub(r'\*\*', '', enhanced_resume)  # Remove bold formatting
            enhanced_resume = re.sub(r'\*', '', enhanced_resume)    # Remove italic formatting
            enhanced_resume = re.sub(r'__', '', enhanced_resume)    # Remove underscore bold
            enhanced_resume = re.sub(r'_', '', enhanced_resume)     # Remove underscore italic
            
            return enhanced_resume, skills_list, keywords_used
            
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON response from Gemini API")
            # Fallback to basic text extraction
            cleaned_text = response.text.strip()
            cleaned_text = re.sub(r'```[a-z]*\n', '', cleaned_text)
            cleaned_text = cleaned_text.replace('```', '')
            
            # Remove all markdown formatting
            cleaned_text = re.sub(r'\*\*', '', cleaned_text)  # Remove bold formatting
            cleaned_text = re.sub(r'\*', '', cleaned_text)    # Remove italic formatting
            cleaned_text = re.sub(r'__', '', cleaned_text)    # Remove underscore bold
            cleaned_text = re.sub(r'_', '', cleaned_text)     # Remove underscore italic
            
            return cleaned_text, [], []
            
    except Exception as e:
        logging.error(f"Error in Gemini API call: {e}")
        raise ValueError(f"Failed to enhance resume: {str(e)}")

def generate_pdf(text: str, output_path: str, template_type: str = "engineering", 
                skills_list: list = None, output_format: str = "standard") -> None:
    """Generate a professionally formatted PDF with the enhanced resume."""
    try:
        # Final cleanup of any markdown formatting before generating PDF
        def clean_markdown(text):
            # Remove any remaining markdown formatting
            text = re.sub(r'\*\*', '', text)  # Remove bold formatting
            text = re.sub(r'\*', '', text)    # Remove italic formatting
            text = re.sub(r'__', '', text)    # Remove underscore bold
            text = re.sub(r'_', '', text)     # Remove underscore italic
            text = re.sub(r'##+\s', '', text) # Remove heading markers
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Replace [text](url) with just text
            return text
            
        # Clean the text before proceeding
        text = clean_markdown(text)
        
        # Create a function to clean text for PDF
        def clean_text_for_pdf(text):
            # First clean any markdown that might be in the line
            text = clean_markdown(text)
            
            # Replace common Unicode characters with ASCII equivalents
            replacements = {
                '\u2013': '-',  # en-dash
                '\u2014': '--',  # em-dash
                '\u2018': "'",  # left single quote
                '\u2019': "'",  # right single quote
                '\u201c': '"',  # left double quote
                '\u201d': '"',  # right double quote
                '\u2022': '*',  # bullet
                '\u2026': '...',  # ellipsis
                '\u00a0': ' ',  # non-breaking space
            }
            
            for unicode_char, ascii_char in replacements.items():
                text = text.replace(unicode_char, ascii_char)
                
            # Final fallback - replace any remaining non-Latin1 chars
            return text.encode('latin-1', 'replace').decode('latin-1')
        
        # Set PDF template based on template_type and output_format
        if output_format == "modern":
            # Use a modern template with better styling
            generate_modern_pdf(text, output_path, template_type, skills_list)
        else:
            # Standard template with basic formatting
            pdf = FPDF(orientation='P', unit='mm', format='A4')
            pdf.add_page()
            
            # Set margins
            pdf.set_margins(15, 15, 15)
            
            # Add header styling based on template type
            if template_type == "faang":
                pdf.set_fill_color(66, 133, 244)  # Google blue
                header_color = (66, 133, 244)
            elif template_type == "non-tech":
                pdf.set_fill_color(121, 85, 72)  # Brown
                header_color = (121, 85, 72)
            else:  # engineering
                pdf.set_fill_color(76, 175, 80)  # Green
                header_color = (76, 175, 80)
                
            # Draw header rectangle
            pdf.rect(0, 0, 210, 15, 'F')
                
            # Add title
            pdf.set_font("Arial", "B", 16)
            pdf.set_text_color(255, 255, 255)  # White text
            pdf.cell(0, 10, "Enhanced Resume", 0, 1, "C")
            
            # Reset text color to black
            pdf.set_text_color(0, 0, 0)
            pdf.ln(10)
            
            # Add resume content
            pdf.set_font("Arial", "", 10)
            
            # Split the text by lines and clean each line
            lines = text.split('\n')
            
            # Process sections
            current_section = ""
            
            for line in lines:
                # Clean the line
                clean_line = clean_text_for_pdf(line)
                
                # Check if line is a section heading (uppercase)
                if clean_line.strip() and clean_line.strip().isupper():
                    current_section = clean_line.strip()
                    
                    # Add spacing before section (except first section)
                    if pdf.get_y() > 30:
                        pdf.ln(5)
                        
                    # Add section heading with styling
                    pdf.set_font("Arial", "B", 12)
                    pdf.set_text_color(*header_color)
                    pdf.cell(0, 8, clean_line, 0, 1)
                    pdf.set_text_color(0, 0, 0)  # Reset to black
                    
                    # Add underline
                    y_position = pdf.get_y()
                    pdf.line(15, y_position, 195, y_position)
                    pdf.ln(2)
                    
                    # Reset font
                    pdf.set_font("Arial", "", 10)
                else:
                    # Process line based on content
                    if clean_line.strip():  # Skip empty lines
                        # Check for bullet points
                        if clean_line.strip().startswith('•') or clean_line.strip().startswith('-') or clean_line.strip().startswith('*'):
                            # Format bullet points with indentation
                            pdf.set_x(20)  # Indent
                            pdf.multi_cell(0, 5, clean_line)
                        else:
                            # Check for likely job titles or dates (bold them)
                            if re.search(r'\b(19|20)\d{2}\b', clean_line) or re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', clean_line):
                                pdf.set_font("Arial", "B", 10)
                                pdf.multi_cell(0, 5, clean_line)
                                pdf.set_font("Arial", "", 10)
                            else:
                                # Normal text
                                pdf.multi_cell(0, 5, clean_line)
                    else:
                        # Empty line - add some spacing
                        pdf.ln(3)
            
            # Add footer
            pdf.set_y(-15)
            pdf.set_font("Arial", "I", 8)
            pdf.cell(0, 10, f"Generated on {datetime.now().strftime('%Y-%m-%d')}", 0, 0, "C")
            
            # Save the PDF
            pdf.output(output_path)
            
    except Exception as e:
        logging.error(f"Error generating PDF: {e}")
        raise

def generate_modern_pdf(text: str, output_path: str, template_type: str, skills_list: list = None) -> None:
    """Generate a modern-looking PDF with better styling and layout."""
    try:
        # Clean any markdown formatting first
        def clean_markdown(text):
            # Remove any remaining markdown formatting
            text = re.sub(r'\*\*', '', text)  # Remove bold formatting
            text = re.sub(r'\*', '', text)    # Remove italic formatting
            text = re.sub(r'__', '', text)    # Remove underscore bold
            text = re.sub(r'_', '', text)     # Remove underscore italic
            text = re.sub(r'##+\s', '', text) # Remove heading markers
            text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)  # Replace [text](url) with just text
            return text
            
        # Clean the text before proceeding
        text = clean_markdown(text)
        
        class ModernPDF(FPDF):
            def header(self):
                # Header with styling based on template type
                if template_type == "faang":
                    self.set_fill_color(66, 133, 244)  # Google blue
                    self.set_text_color(66, 133, 244)
                elif template_type == "non-tech":
                    self.set_fill_color(121, 85, 72)  # Brown
                    self.set_text_color(121, 85, 72)
                else:  # engineering
                    self.set_fill_color(76, 175, 80)  # Green
                    self.set_text_color(76, 175, 80)
                
                # Add colored rectangle at top
                self.rect(0, 0, 210, 20, 'F')
                
                # Add title
                self.set_font('Arial', 'B', 18)
                self.set_text_color(255, 255, 255)
                self.cell(0, 15, "Professional Resume", 0, 1, 'C')
                
                # Reset text color
                if template_type == "faang":
                    self.set_text_color(66, 133, 244)
                elif template_type == "non-tech":
                    self.set_text_color(121, 85, 72)
                else:
                    self.set_text_color(76, 175, 80)
                
                # Set line below header
                self.line(10, 23, 200, 23)
                
                # Add some space after header
                self.ln(15)
            
            def footer(self):
                # Go to bottom of page
                self.set_y(-15)
                self.set_font('Arial', 'I', 8)
                self.set_text_color(128, 128, 128)  # Gray
                
                # Add page number and date
                self.cell(0, 10, f"Generated on {datetime.now().strftime('%Y-%m-%d')} - Page {self.page_no()}", 0, 0, 'C')
        
        # Create PDF with custom class
        pdf = ModernPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        
        # Create a function to clean text for PDF
        def clean_text_for_pdf(text):
            # Replace common Unicode characters with ASCII equivalents
            replacements = {
                '\u2013': '-',  # en-dash
                '\u2014': '--',  # em-dash
                '\u2018': "'",  # left single quote
                '\u2019': "'",  # right single quote
                '\u201c': '"',  # left double quote
                '\u201d': '"',  # right double quote
                '\u2022': '*',  # bullet
                '\u2026': '...',  # ellipsis
                '\u00a0': ' ',  # non-breaking space
            }
            
            for unicode_char, ascii_char in replacements.items():
                text = text.replace(unicode_char, ascii_char)
                
            # Final fallback - replace any remaining non-Latin1 chars
            return text.encode('latin-1', 'replace').decode('latin-1')
        
        # Split the text by lines and clean
        lines = text.split('\n')
        
        # Set color based on template type
        if template_type == "faang":
            section_color = (66, 133, 244)  # Google blue
        elif template_type == "non-tech":
            section_color = (121, 85, 72)  # Brown
        else:  # engineering
            section_color = (76, 175, 80)  # Green
        
        # Process sections
        current_section = ""
        in_bullet_list = False
        
        for line in lines:
            # Clean the line
            clean_line = clean_text_for_pdf(line)
            
            # Skip empty lines
            if not clean_line.strip():
                pdf.ln(2)
                in_bullet_list = False
                continue
            
            # Check if line is a section heading (uppercase)
            if clean_line.strip() and clean_line.strip().isupper():
                current_section = clean_line.strip()
                
                # Add spacing before section (except first section)
                if pdf.get_y() > 40:
                    pdf.ln(5)
                
                # Add section heading with styling
                pdf.set_font("Arial", "B", 12)
                pdf.set_text_color(*section_color)
                
                # Add small rectangle before section title
                current_y = pdf.get_y()
                pdf.rect(10, current_y, 4, 6, 'F')
                pdf.set_x(16)  # Move text position after rectangle
                
                pdf.cell(0, 6, clean_line, 0, 1)
                
                # Add underline
                y_position = pdf.get_y() + 1
                pdf.line(10, y_position, 200, y_position)
                pdf.ln(4)
                
                # Reset text color to black
                pdf.set_text_color(0, 0, 0)
                in_bullet_list = False
                
            else:
                # Process special lines
                # Job titles or dates (bold them)
                if re.search(r'\b(19|20)\d{2}\b', clean_line) or re.search(r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b', clean_line):
                    pdf.set_font("Arial", "B", 11)
                    pdf.cell(0, 6, clean_line, 0, 1)
                    pdf.set_font("Arial", "", 10)
# Reset to normal font
                    pdf.set_font("Arial", "", 10)
                    in_bullet_list = False
                
                # Check for bullet points
                elif clean_line.strip().startswith('•') or clean_line.strip().startswith('-') or clean_line.strip().startswith('*'):
                    if not in_bullet_list:
                        # Start a new bullet list with some spacing
                        pdf.ln(1)
                    
                    # Format bullet point with proper indentation
                    pdf.set_x(15)  # Indent
                    pdf.set_font("Arial", "", 10)
                    pdf.multi_cell(0, 5, clean_line, 0, 'L')
                    in_bullet_list = True
                
                # Regular text - handle based on content
                else:
                    # Check if it might be a company or organization name
                    if clean_line.strip() and pdf.get_font()[1] != 'B' and current_section.lower().find("experience") >= 0:
                        pdf.set_font("Arial", "B", 10)
                        pdf.cell(0, 6, clean_line, 0, 1)
                        pdf.set_font("Arial", "", 10)
                    else:
                        # Normal paragraph text
                        pdf.set_font("Arial", "", 10)
                        pdf.multi_cell(0, 5, clean_line, 0, 'L')
                    
                    in_bullet_list = False
                
        # Add skills section if available
        if skills_list and len(skills_list) > 0:
            pdf.add_page()
            
            # Add skills section header
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(*section_color)
            
            # Add small rectangle before section title
            current_y = pdf.get_y()
            pdf.rect(10, current_y, 4, 6, 'F')
            pdf.set_x(16)  # Move text position after rectangle
            
            pdf.cell(0, 6, "KEY SKILLS", 0, 1)
            
            # Add underline
            y_position = pdf.get_y() + 1
            pdf.line(10, y_position, 200, y_position)
            pdf.ln(10)
            
            # Reset text color to black
            pdf.set_text_color(0, 0, 0)
            
            # Create a 2-column layout for skills
            skills_per_column = (len(skills_list) + 1) // 2
            column_width = 90
            
            # First column
            pdf.set_x(20)
            pdf.set_font("Arial", "", 10)
            
            for i, skill in enumerate(skills_list):
                if i < skills_per_column:
                    pdf.set_x(20)
                    pdf.cell(column_width, 8, f"• {skill}", 0, 1)
                else:
                    if i == skills_per_column:
                        # Reset Y position for second column
                        pdf.set_y(pdf.get_y() - (8 * skills_per_column))
                    
                    pdf.set_x(120)
                    pdf.cell(column_width, 8, f"• {skill}", 0, 1)
        
        # Save the PDF
        pdf.output(output_path)
        
    except Exception as e:
        logging.error(f"Error generating modern PDF: {e}")
        raise

def calculate_match_score(resume_text: str, job_description: str) -> int:
    """Calculate a match score between the resume and job description."""
    try:
        # Use Gemini to calculate the match score
        prompt = f"""
        You are an expert ATS (Applicant Tracking System) analyzer. Please evaluate how well this resume 
        matches the job description. Calculate a score from 0-100 based on:
        
        1. Keyword match (how many important keywords from the job description appear in the resume)
        2. Skills alignment (how well the candidate's skills match the required and preferred skills)
        3. Experience relevance (how relevant the candidate's experience is to the role)
        4. Education/certification match (if applicable)
        
        Resume:
        ```
        {resume_text}
        ```
        
        Job Description:
        ```
        {job_description}
        ```
        
        Return only a single integer score between 0 and 100. Do not include any explanations.
        """
        
        # Use lower temperature for more consistent results
        response = model.generate_content(
            contents=prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                max_output_tokens=10
            )
        )
        
        # Extract the score from the response
        score_text = response.text.strip()
        
        # Try to convert to integer
        try:
            score = int(score_text)
            # Ensure score is within valid range
            if score < 0:
                score = 0
            elif score > 100:
                score = 100
            return score
        except ValueError:
            # Fallback value if response is not a valid integer
            logging.warning(f"Invalid match score response: {score_text}")
            return 65  # Default middle-range score
            
    except Exception as e:
        logging.error(f"Error calculating match score: {e}")
        return 50  # Default score on error

# Additional helper functions for handling images and visual elements
def create_text_image(text, width=800, height=1000, bg_color=(255, 255, 255), 
                     text_color=(0, 0, 0), font_size=14):
    """Create an image containing formatted text."""
    # Create a blank image
    image = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(image)
    
    # Try to load a font, fallback to default if not available
    try:
        font_path = os.path.join(FONTS_FOLDER, "Roboto-Regular.ttf")
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        # Use default font
        font = ImageFont.load_default()
    
    # Wrap text to fit the image width
    margin = 20
    max_width = width - 2 * margin
    lines = []
    
    for paragraph in text.split('\n'):
        if paragraph.strip():
            wrapped_lines = textwrap.wrap(paragraph, width=max_width // (font_size // 2))
            lines.extend(wrapped_lines)
            lines.append('')  # Add blank line between paragraphs
        else:
            lines.append('')  # Preserve empty lines
    
    # Draw text
    y_position = margin
    for line in lines:
        draw.text((margin, y_position), line, font=font, fill=text_color)
        y_position += font_size + 4
        
        # Check if we need a new page (image)
        if y_position > height - margin:
            break
    
    return image

def image_to_base64(image):
    """Convert PIL Image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

@app.route("/api/chat-with-resume", methods=["POST"])
def chat_with_resume():
    """API endpoint to chat with and modify a resume using Gemini."""
    try:
        logging.info("Chat with resume request received")
        
        # Get data from the request
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        user_message = data.get("message", "")
        resume_text = data.get("resumeText", "")
        job_description = data.get("jobDescription", "")
        template_type = data.get("template", "engineering")
        output_format = data.get("outputFormat", "standard")
        
        if not user_message:
            return jsonify({"error": "Message is required"}), 400
            
        if not resume_text:
            return jsonify({"error": "Resume text is required"}), 400
        
        # Create a unique ID for this conversation
        conversation_id = str(uuid.uuid4())
        
        # Process the chat and get a response with optional resume updates
        try:
            response, updated_resume, skills_list, keywords_used = process_chat_with_resume(
                user_message, resume_text, job_description, template_type
            )
            logging.info("Chat processed successfully")
        except Exception as e:
            logging.error(f"Error processing chat: {e}")
            return jsonify({"error": f"Failed to process chat: {str(e)}"}), 500
        
        # If resume was updated, generate new PDF
        pdf_url = None
        txt_url = None
        match_score = None
        
        if updated_resume and updated_resume != resume_text:
            logging.info("Resume was updated, generating files")
            
            # Generate PDF of the updated resume
            pdf_filename = f"updated_resume_{conversation_id}.pdf"
            pdf_path = os.path.join(OUTPUT_FOLDER, pdf_filename)
            
            try:
                # Make sure the OUTPUT_FOLDER exists
                os.makedirs(OUTPUT_FOLDER, exist_ok=True)
                
                # Generate PDF
                generate_pdf(updated_resume, pdf_path, template_type, skills_list, output_format)
                logging.info(f"Updated PDF generated: {pdf_path}")
                
                # Verify that the file was created
                if os.path.exists(pdf_path):
                    pdf_url = url_for('download_resume', filename=pdf_filename, type='pdf')
                    logging.info(f"PDF URL created: {pdf_url}")
                else:
                    logging.error(f"PDF file was not created at {pdf_path}")
            except Exception as e:
                logging.error(f"Error generating updated PDF: {str(e)}")
                # Continue without PDF - we'll still return the text version
            
            # Generate a text version for download
            txt_filename = f"updated_resume_{conversation_id}.txt"
            txt_path = os.path.join(OUTPUT_FOLDER, txt_filename)
            
            try:
                with open(txt_path, 'w', encoding='utf-8') as f:
                    f.write(updated_resume)
                
                if os.path.exists(txt_path):
                    txt_url = url_for('download_resume', filename=txt_filename, type='txt')
                    logging.info(f"TXT URL created: {txt_url}")
                else:
                    logging.error(f"TXT file was not created at {txt_path}")
            except Exception as e:
                logging.error(f"Error generating text file: {str(e)}")
            
            # Generate a match score between the updated resume and job description
            try:
                match_score = calculate_match_score(updated_resume, job_description)
                logging.info(f"Match score calculated: {match_score}")
            except Exception as e:
                logging.error(f"Error calculating match score: {str(e)}")
                match_score = None
        
        # Prepare the response
        response_data = {
            "response": response
        }
        
        if updated_resume and updated_resume != resume_text:
            response_data.update({
                "updatedResume": updated_resume,
                "pdfUrl": pdf_url,
                "txtUrl": txt_url,
                "matchScore": match_score,
                "skills": skills_list,
                "keywordsUsed": keywords_used
            })
            logging.info(f"Returning updated resume data with download URLs")
        
        return jsonify(response_data)
        
    except Exception as e:
        logging.error(f"Unexpected error in chat_with_resume: {e}")
        return jsonify({"error": str(e)}), 500


def process_chat_with_resume(user_message: str, resume_text: str, job_description: str, template_type: str) -> tuple:
    """
    Process a chat message about a resume and return a response with optional resume updates.
    Ensures proper formatting is maintained.
    """
    try:
        # Create a prompt for Gemini to handle the chat
        prompt_template = """
        You are an AI resume assistant helping a user modify their resume through a chat interface.
        
        # User's current resume:
        ```
        {resume_text}
        ```
        
        # Job description they're applying for:
        ```
        {job_description}
        ```
        
        # User's message to you:
        ```
        {user_message}
        ```
        
        ## Instructions:
        1. If the user is asking for modifications to their resume, make the requested changes while STRICTLY preserving the overall format and structure.
        2. Maintain all section headers, indentation, and spacing exactly as in the original resume.
        3. Keep the same line break pattern as the original resume.
        4. If you're adding new content, follow the exact same formatting style as similar content in the resume.
        5. Do not reformat or rearrange sections unless specifically requested by the user.
        6. Your role is to be conversational but focused on helping improve the resume for the specific job.
        7. If you make changes to the resume, explain what changes you made and why they improve the resume.
        
        Your output must be in this JSON format:
        {{
            "response": "Your conversational response to the user explaining what you did or giving advice",
            "resume_updated": true/false,
            "updated_resume": "The full updated resume text if changes were made, otherwise null",
            "skills_list": ["Skill 1", "Skill 2", "Skill 3"...],  // List of 5-10 most important skills (only if resume was updated)
            "keywords_used": ["Keyword 1", "Keyword 2", "Keyword 3"...]  // List of keywords from job description used in the resume (only if resume was updated)
        }}
        """
        
        # Format the prompt with the actual data
        formatted_prompt = prompt_template.format(
            user_message=user_message,
            resume_text=resume_text,
            job_description=job_description
        )
        
        # Use Gemini Pro to process the chat
        response = model.generate_content(
            contents=formatted_prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,  # Lower temperature for more precise formatting
                max_output_tokens=4000,  # Higher token limit for longer responses
                response_mime_type="application/json"  # Request JSON response
            )
        )
        
        # Check if we have a valid response
        if not response.text:
            logging.error("Empty or invalid response from Gemini API")
            return "Sorry, I couldn't process your request. Please try again.", None, [], []
        
        # Parse the JSON response
        try:
            result = json.loads(response.text)
            ai_response = result.get("response", "")
            resume_updated = result.get("resume_updated", False)
            updated_resume = result.get("updated_resume", None) if resume_updated else None
            skills_list = result.get("skills_list", []) if resume_updated else []
            keywords_used = result.get("keywords_used", []) if resume_updated else []
            
            # Clean up the updated resume text if it exists
            if updated_resume:
                updated_resume = updated_resume.strip()
                
                # Remove any markdown code blocks if present
                updated_resume = re.sub(r'```[a-z]*\n', '', updated_resume)
                updated_resume = updated_resume.replace('```', '')
                
                # Remove any markdown formatting
                updated_resume = re.sub(r'\*\*', '', updated_resume)  # Remove bold
                updated_resume = re.sub(r'\_\_', '', updated_resume)  # Remove underline
                updated_resume = re.sub(r'\*', '', updated_resume)    # Remove italics
                updated_resume = re.sub(r'\_', '', updated_resume)    # Remove italics
            
            return ai_response, updated_resume, skills_list, keywords_used
            
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON response from Gemini API")
            # Try to extract a basic text response
            return "I processed your request, but couldn't format the response properly. Please try again with a clearer request.", None, [], []
            
    except Exception as e:
        logging.error(f"Error in Gemini API call for chat: {e}")
        raise ValueError(f"Failed to process chat: {str(e)}")
    
if __name__ == "__main__":
    # Run the Flask app
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)