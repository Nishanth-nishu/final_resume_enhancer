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

@app.route("/download-resume/<filename>")
def download_resume(filename):
    """Serve the generated resume file for download."""
    try:
        file_type = request.args.get('type', 'pdf')
        file_path = os.path.join(OUTPUT_FOLDER, filename)
        
        if not os.path.exists(file_path):
            logging.error(f"File not found: {file_path}")
            return jsonify({"error": "File not found"}), 404
            
        if file_type == 'pdf':
            return send_file(file_path, as_attachment=True, download_name="enhanced_resume.pdf")
        else:
            return send_file(file_path, as_attachment=True, download_name="enhanced_resume.txt")
    except Exception as e:
        logging.error(f"Error serving file: {e}")
        return jsonify({"error": str(e)}), 500

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
            
            return enhanced_resume, skills_list, keywords_used
            
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON response from Gemini API")
            # Fallback to basic text extraction
            cleaned_text = response.text.strip()
            cleaned_text = re.sub(r'```[a-z]*\n', '', cleaned_text)
            cleaned_text = cleaned_text.replace('```', '')
            return cleaned_text, [], []
            
    except Exception as e:
        logging.error(f"Error in Gemini API call: {e}")
        raise ValueError(f"Failed to enhance resume: {str(e)}")

def generate_pdf(text: str, output_path: str, template_type: str = "engineering", 
                skills_list: list = None, output_format: str = "standard") -> None:
    """Generate a professionally formatted PDF with the enhanced resume."""
    try:
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
@app.route("/api/download-tailored", methods=["POST"])
def download_tailored_resume():
    """API endpoint to generate and download a tailored resume."""
    try:
        logging.info("Download tailored resume request received")
        
        # Get the enhanced resume text and job description from the request
        data = request.json
        if not data:
            return jsonify({"error": "No data provided"}), 400
            
        enhanced_resume = data.get("enhancedResume", "")
        job_description = data.get("jobDescription", "")
        template_type = data.get("template", "engineering")
        output_format = data.get("outputFormat", "standard")
        
        if not enhanced_resume:
            return jsonify({"error": "Enhanced resume text is required"}), 400
            
        if not job_description:
            return jsonify({"error": "Job description is required"}), 400
        
        # Create a unique ID for this download
        unique_id = str(uuid.uuid4())
        
        # Further tailor the resume specifically for this job
        try:
            tailored_resume, skills_list, keywords_used = tailor_resume_for_job(
                enhanced_resume, job_description, template_type
            )
            logging.info("Resume tailored successfully")
        except Exception as e:
            logging.error(f"Error tailoring resume: {e}")
            return jsonify({"error": f"Failed to tailor resume: {str(e)}"}), 500
        
        # Generate PDF of the tailored resume
        pdf_filename = f"tailored_resume_{unique_id}.pdf"
        pdf_path = os.path.join(OUTPUT_FOLDER, pdf_filename)
        
        try:
            generate_pdf(tailored_resume, pdf_path, template_type, skills_list, output_format)
            logging.info(f"Tailored PDF generated: {pdf_path}")
        except Exception as e:
            logging.error(f"Error generating tailored PDF: {e}")
            return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500
        
        # Generate a text version for download
        txt_filename = f"tailored_resume_{unique_id}.txt"
        txt_path = os.path.join(OUTPUT_FOLDER, txt_filename)
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(tailored_resume)
        
        # Generate a match score between the tailored resume and job description
        match_score = calculate_match_score(tailored_resume, job_description)
        
        return jsonify({
            "tailoredResume": tailored_resume,
            "pdfUrl": url_for('download_resume', filename=pdf_filename, type='pdf'),
            "txtUrl": url_for('download_resume', filename=txt_filename, type='txt'),
            "matchScore": match_score,
            "keywordsUsed": keywords_used,
            "skills": skills_list
        })
        
    except Exception as e:
        logging.error(f"Unexpected error in download_tailored_resume: {e}")
        return jsonify({"error": str(e)}), 500

def tailor_resume_for_job(resume_text: str, job_description: str, template_type: str) -> tuple:
    """Further tailor an already enhanced resume specifically for a job."""
    try:
        # Select prompt template based on template_type
        prompt_template = """
        You are an expert resume editor specializing in job-specific tailoring.
        
        I already have an enhanced resume, but I need you to further tailor it specifically for this job description.
        
        Focus on:
        1. Reordering skills and experiences to highlight those most relevant to this specific job
        2. Adjusting wording to better match the terminology used in the job description
        3. Emphasizing achievements that directly relate to the key requirements
        4. Ensuring all critical keywords from the job description are incorporated naturally
        5. Adapting the professional summary to address the specific role
        6. Making sure the resume passes ATS screening for this exact position
        
        Enhanced Resume to tailor:
        ```
        {resume_text}
        ```
        
        Job Description:
        ```
        {job_description}
        ```
        
        Your output must be in this JSON format:
        {{
            "tailored_resume": "The complete tailored resume as plain text with professional formatting",
            "skills_list": ["Skill 1", "Skill 2", "Skill 3"...],  // List of 5-10 most important skills for this specific job
            "keywords_used": ["Keyword 1", "Keyword 2", "Keyword 3"...]  // List of keywords from job description used in the resume
        }}
        
        Ensure the tailored resume maintains professional formatting in plain text.
        """
        
        # Format the prompt with the actual resume and job description
        formatted_prompt = prompt_template.format(
            resume_text=resume_text,
            job_description=job_description
        )
        
        # Use Gemini Pro to generate the tailored resume
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
            return "Error: Could not generate tailored resume. Please try again.", [], []
        
        # Parse the JSON response
        try:
            result = json.loads(response.text)
            tailored_resume = result.get("tailored_resume", "")
            skills_list = result.get("skills_list", [])
            keywords_used = result.get("keywords_used", [])
            
            # Clean the tailored resume text
            tailored_resume = tailored_resume.strip()
            
            # Remove any markdown code blocks if present
            tailored_resume = re.sub(r'```[a-z]*\n', '', tailored_resume)
            tailored_resume = tailored_resume.replace('```', '')
            
            return tailored_resume, skills_list, keywords_used
            
        except json.JSONDecodeError:
            logging.error("Failed to parse JSON response from Gemini API")
            # Fallback to basic text extraction
            cleaned_text = response.text.strip()
            cleaned_text = re.sub(r'```[a-z]*\n', '', cleaned_text)
            cleaned_text = cleaned_text.replace('```', '')
            return cleaned_text, [], []
            
    except Exception as e:
        logging.error(f"Error in Gemini API call for tailoring: {e}")
        raise ValueError(f"Failed to tailor resume: {str(e)}")
    
if __name__ == "__main__":
    # Run the Flask app
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)