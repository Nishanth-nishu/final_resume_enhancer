from flask import Flask, request, jsonify, render_template, send_file, url_for
import os
from google import genai  # Updated import
from dotenv import load_dotenv
import logging
import tempfile
from werkzeug.utils import secure_filename
import uuid
import json
from fpdf import FPDF
import re
from datetime import datetime

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__, static_folder='static')

# Configure Gemini API
GEMINI_API_KEY = "AIzaSyCa7KsetFdZqB5gf4Ex6gtQHet2-Mobcj8"
if not GEMINI_API_KEY:
    logging.error("GEMINI_API_KEY environment variable not set!")
    raise ValueError("GEMINI_API_KEY not configured")

# Ensure necessary directories exist
UPLOAD_FOLDER = "uploads"
OUTPUT_FOLDER = "enhanced_resumes"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)
os.makedirs(os.path.join("static", "js"), exist_ok=True)

# File configuration
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'txt'}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB

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
        # Get uploaded file and job description
        if 'resume' not in request.files:
            return jsonify({"error": "No resume file uploaded"}), 400
            
        resume_file = request.files['resume']
        
        if resume_file.filename == '':
            return jsonify({"error": "No file selected"}), 400
            
        if not allowed_file(resume_file.filename):
            return jsonify({"error": f"Only {', '.join(ALLOWED_EXTENSIONS)} files are allowed"}), 400
            
        # Check file size
        resume_file.seek(0, os.SEEK_END)
        file_size = resume_file.tell()
        resume_file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({"error": "File size exceeds 5MB limit"}), 400
            
        job_description = request.form.get("jobDescription", "")
        template_type = request.form.get("template", "engineering")
        
        if not job_description:
            return jsonify({"error": "Job description is required"}), 400

        # Create a unique filename
        filename = secure_filename(resume_file.filename)
        unique_id = str(uuid.uuid4())
        file_extension = os.path.splitext(filename)[1]
        secure_filename_with_id = f"{unique_id}{file_extension}"
        file_path = os.path.join(UPLOAD_FOLDER, secure_filename_with_id)
        
        # Save the uploaded file
        resume_file.save(file_path)
        
        # Extract text from the resume
        try:
            resume_text = extract_resume_text(file_path)
        except Exception as e:
            logging.error(f"Error extracting text: {e}")
            os.remove(file_path)  # Clean up the file
            return jsonify({"error": f"Could not extract text from file: {str(e)}"}), 400
            
        # Enhance resume using Gemini API with appropriate template
        enhanced_resume = enhance_resume_with_gemini(resume_text, job_description, template_type)
        
        # Generate PDF of the enhanced resume
        pdf_filename = f"enhanced_resume_{unique_id}.pdf"
        pdf_path = os.path.join(OUTPUT_FOLDER, pdf_filename)
        
        try:
            generate_pdf(enhanced_resume, pdf_path)
        except Exception as e:
            logging.error(f"Error generating PDF: {e}")
            return jsonify({"error": f"PDF generation failed: {str(e)}"}), 500

        return jsonify({
            "originalResume": resume_text,
            "enhancedResume": enhanced_resume,
            "pdfUrl": url_for('download_resume', filename=pdf_filename)
        })
        
    except Exception as e:
        logging.error(f"Error enhancing resume: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/download-resume/<filename>")
def download_resume(filename):
    """Serve the generated PDF resume for download."""
    pdf_path = os.path.join(OUTPUT_FOLDER, filename)
    if not os.path.exists(pdf_path):
        return jsonify({"error": "File not found"}), 404
    return send_file(pdf_path, as_attachment=True, download_name="enhanced_resume.pdf")

def extract_resume_text(file_path: str) -> str:
    """Extract text from a resume file (PDF, DOCX, or TXT)."""
    try:
        if file_path.endswith(".pdf"):
            from pdfminer.high_level import extract_text
            text = extract_text(file_path)
            return text if text.strip() else "No text could be extracted from PDF"
            
        elif file_path.endswith(".docx"):
            from docx import Document
            doc = Document(file_path)
            return "\n".join([para.text for para in doc.paragraphs])
            
        elif file_path.endswith(".txt"):
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
        else:
            raise ValueError(f"Unsupported file format: {file_path}")
    except Exception as e:
        logging.error(f"Error in extract_resume_text: {e}")
        raise

def enhance_resume_with_gemini(resume_text: str, job_description: str, template_type: str) -> str:
    """Enhance the resume text using Gemini API with appropriate template."""
    
    # Configure the client with API key
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Select prompt template based on template_type
    if template_type == "faang":
        prompt_template = """
        You are an expert resume editor for FAANG companies (Facebook, Amazon, Apple, Netflix, Google).
        
        Please enhance the following resume to target the job description provided. 
        
        Focus on:
        1. Using quantifiable achievements and metrics
        2. Highlighting technical skills and projects relevant to the job
        3. Using action verbs and demonstrating impact
        4. Removing irrelevant information
        5. Organizing content for maximum readability
        6. Using STAR methodology (Situation, Task, Action, Result) for experiences
        7. Making sure the resume is ATS-friendly (Applicant Tracking System)
        
        Resume to enhance:
        ```
        {resume_text}
        ```
        
        Job Description:
        ```
        {job_description}
        ```
        
        Generate a well-formatted plain text version of the enhanced resume that maintains professional formatting.
        Return ONLY the enhanced resume content with no additional commentary.
        """
    elif template_type == "non-tech":
        prompt_template = """
        You are an expert resume editor for non-technical professionals.
        
        Please enhance the following resume to target the job description provided.
        
        Focus on:
        1. Highlighting transferable skills and relevant accomplishments
        2. Using industry-specific terminology from the job description
        3. Emphasizing soft skills and interpersonal abilities
        4. Quantifying achievements whenever possible
        5. Ensuring clear organization and professional formatting
        6. Tailoring the professional summary to match the job requirements
        7. Making sure the resume is ATS-friendly (Applicant Tracking System)
        
        Resume to enhance:
        ```
        {resume_text}
        ```
        
        Job Description:
        ```
        {job_description}
        ```
        
        Generate a well-formatted plain text version of the enhanced resume that maintains professional formatting.
        Return ONLY the enhanced resume content with no additional commentary.
        """
    else:  # Default to engineering template
        prompt_template = """
        You are an expert resume editor for engineering professionals.
        
        Please enhance the following resume to target the job description provided.
        
        Focus on:
        1. Highlighting relevant technical skills and engineering achievements
        2. Using proper engineering terminology aligned with the job description
        3. Emphasizing problem-solving abilities and technical solutions
        4. Quantifying results and impact where possible
        5. Organizing content for maximum readability
        6. Including relevant projects, technologies, and methodologies
        7. Making sure the resume is ATS-friendly (Applicant Tracking System)
        
        Resume to enhance:
        ```
        {resume_text}
        ```
        
        Job Description:
        ```
        {job_description}
        ```
        
        Generate a well-formatted plain text version of the enhanced resume that maintains professional formatting.
        Return ONLY the enhanced resume content with no additional commentary.
        """
    
    # Format the prompt with the actual resume and job description
    formatted_prompt = prompt_template.format(
        resume_text=resume_text,
        job_description=job_description
    )
    
    try:
        # Use the updated API method format
        response = client.models.generate_content(
            model="gemini-2.0-flash", 
            contents=formatted_prompt,
            safety_settings=[
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        )
        
        # Check if we have a valid response
        if not hasattr(response, 'text') or not response.text:
            logging.error("Empty or invalid response from Gemini API")
            return "Error: Could not generate enhanced resume. Please try again."
            
        # Clean the response text to ensure it's just the resume content
        cleaned_text = response.text.strip()
        
        # Remove any markdown code blocks if present
        cleaned_text = re.sub(r'```[a-z]*\n', '', cleaned_text)
        cleaned_text = cleaned_text.replace('```', '')
        
        return cleaned_text
        
    except Exception as e:
        logging.error(f"Error in Gemini API call: {e}")
        raise ValueError(f"Failed to enhance resume: {str(e)}")

def generate_pdf(text: str, output_path: str) -> None:
    """Generate a PDF with the enhanced resume."""
    pdf = FPDF()
    pdf.add_page()
    
    # Add header
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, "Enhanced Resume", 0, 1, "C")
    pdf.line(10, 20, 200, 20)
    pdf.ln(5)
    
    # Add resume content
    pdf.set_font("Arial", "", 10)
    
    # Split the text by lines
    lines = text.split('\n')
    
    for line in lines:
        # Check if line is a heading (assumes headings are capitalized)
        if line.strip() and line.strip().isupper():
            pdf.set_font("Arial", "B", 12)
            pdf.cell(0, 10, line, 0, 1)
            pdf.set_font("Arial", "", 10)
        else:
            # Wrap text to fit page width
            pdf.multi_cell(0, 5, line)
    
    # Add footer with date
    pdf.set_y(-15)
    pdf.set_font("Arial", "I", 8)
    pdf.cell(0, 10, f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", 0, 0, "C")
    
    # Save the PDF
    pdf.output(output_path)

# Create a simple JavaScript file for frontend interactions
@app.route("/static/js/script.js")
def serve_js():
    js_content = """
    document.addEventListener('DOMContentLoaded', function() {
        const dropZone = document.getElementById('drop-zone');
        const fileInput = document.getElementById('resume-upload');
        const uploadStatus = document.getElementById('upload-status');
        const fileName = document.getElementById('file-name');
        const enhanceButton = document.getElementById('enhance-resume');
        const resultsPreview = document.getElementById('results-preview');
        const beforeResume = document.getElementById('before-resume');
        const afterResume = document.getElementById('after-resume');
        const downloadLink = document.getElementById('download-link');
        
        // Handle drag and drop
        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, preventDefaults, false);
        });
        
        function preventDefaults(e) {
            e.preventDefault();
            e.stopPropagation();
        }
        
        ['dragenter', 'dragover'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.add('dragover');
            }, false);
        });
        
        ['dragleave', 'drop'].forEach(eventName => {
            dropZone.addEventListener(eventName, () => {
                dropZone.classList.remove('dragover');
            }, false);
        });
        
        dropZone.addEventListener('drop', handleDrop, false);
        
        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            fileInput.files = files;
            handleFiles(files);
        }
        
        dropZone.addEventListener('click', () => {
            fileInput.click();
        });
        
        fileInput.addEventListener('change', () => {
            handleFiles(fileInput.files);
        });
        
        function handleFiles(files) {
            if (files.length) {
                uploadStatus.classList.remove('hidden');
                fileName.textContent = files[0].name;
                
                // Check file size
                if (files[0].size > 5 * 1024 * 1024) {
                    alert('File size must be less than 5MB');
                    uploadStatus.classList.add('hidden');
                    return;
                }
                
                // Check file type
                const fileExt = files[0].name.split('.').pop().toLowerCase();
                if (!['pdf', 'docx', 'txt'].includes(fileExt)) {
                    alert('Only PDF, DOCX, and TXT files are allowed');
                    uploadStatus.classList.add('hidden');
                    return;
                }
            }
        }
        
        enhanceButton.addEventListener('click', async () => {
            const resumeFile = fileInput.files[0];
            const jobDescription = document.getElementById('job-description').value;
            const template = document.getElementById('resume-template').value;
            
            if (!resumeFile) {
                alert('Please upload a resume file');
                return;
            }
            
            if (!jobDescription) {
                alert('Please enter a job description');
                return;
            }
            
            enhanceButton.textContent = 'Processing...';
            enhanceButton.disabled = true;
            
            const formData = new FormData();
            formData.append('resume', resumeFile);
            formData.append('jobDescription', jobDescription);
            formData.append('template', template);
            
            try {
                const response = await fetch('/api/enhance-resume', {
                    method: 'POST',
                    body: formData
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    beforeResume.textContent = data.originalResume;
                    afterResume.textContent = data.enhancedResume;
                    downloadLink.href = data.pdfUrl;
                    resultsPreview.classList.remove('hidden');
                    
                    // Scroll to results
                    resultsPreview.scrollIntoView({ behavior: 'smooth' });
                } else {
                    alert(`Error: ${data.error}`);
                }
            } catch (error) {
                alert('An error occurred while processing your request');
                console.error(error);
            } finally {
                enhanceButton.textContent = 'Enhance My Resume';
                enhanceButton.disabled = false;
            }
        });
    });
    """
    return js_content, 200, {'Content-Type': 'application/javascript'}

if __name__ == "__main__":
    app.run(debug=True)