# main.py
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import uvicorn
import os
import tempfile
from datetime import datetime
import json
import re
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
import PyPDF2
import docx
import openai
from dotenv import load_dotenv

# Download NLTK resources
nltk.download('punkt')
nltk.download('stopwords')

# Load environment variables
load_dotenv()

# Initialize OpenAI API
openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Resume Enhancement API")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Set to specific origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Models
class EnhancementRequest(BaseModel):
    resume_text: str
    job_description: str

class BulletPoint(BaseModel):
    original: str
    enhanced: str
    
class EnhancementResponse(BaseModel):
    enhanced_bullet_points: List[BulletPoint]
    missing_skills: List[str]
    strong_skills: List[str]
    matched_keywords: List[str]
    ats_score: int

# Helper functions
def extract_text_from_pdf(file_path):
    """Extract text from a PDF file."""
    with open(file_path, 'rb') as file:
        reader = PyPDF2.PdfReader(file)
        text = ""
        for page_num in range(len(reader.pages)):
            text += reader.pages[page_num].extract_text()
    return text

def extract_text_from_docx(file_path):
    """Extract text from a DOCX file."""
    doc = docx.Document(file_path)
    text = ""
    for paragraph in doc.paragraphs:
        text += paragraph.text + "\n"
    return text

def extract_bullet_points(text):
    """Extract bullet points from resume text."""
    # Pattern to match common bullet point formats
    bullet_patterns = [
        r'•\s*(.*?)(?=•|\n\n|\n•|\Z)',
        r'○\s*(.*?)(?=○|\n\n|\n○|\Z)',
        r'▪\s*(.*?)(?=▪|\n\n|\n▪|\Z)',
        r'▫\s*(.*?)(?=▫|\n\n|\n▫|\Z)',
        r'➢\s*(.*?)(?=➢|\n\n|\n➢|\Z)',
        r'→\s*(.*?)(?=→|\n\n|\n→|\Z)',
        r'✓\s*(.*?)(?=✓|\n\n|\n✓|\Z)',
        r'\*\s*(.*?)(?=\*|\n\n|\n\*|\Z)',
        r'-\s*(.*?)(?=-|\n\n|\n-|\Z)',
        r'(?m)^\s*\d+\.\s+(.*?)(?=^\s*\d+\.|\Z)',
    ]
    
    bullet_points = []
    for pattern in bullet_patterns:
        matches = re.finditer(pattern, text, re.DOTALL)
        for match in matches:
            point = match.group(1).strip()
            if point and len(point) > 10:  # Only consider substantial bullet points
                bullet_points.append(point)
                
    # If no bullet points are found, try to split by lines
    if not bullet_points:
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for line in lines:
            if 20 < len(line) < 200 and not line.endswith(':'):
                bullet_points.append(line)
    
    return bullet_points

def extract_skills_from_job_description(job_description):
    """Extract potential skills from the job description."""
    # Common skill-related keywords
    skill_indicators = ['skills', 'requirements', 'qualifications', 'experience with', 'proficient in', 'knowledge of']
    
    # Tokenize the job description
    tokens = word_tokenize(job_description.lower())
    stop_words = set(stopwords.words('english'))
    filtered_tokens = [token for token in tokens if token.isalnum() and token not in stop_words]
    
    # Extract technical terms and potential skills
    # This is a simple approach - in production, we would use a more sophisticated NER model
    skills = []
    technical_terms = ['python', 'java', 'javascript', 'html', 'css', 'react', 'node', 'sql', 'nosql', 
                       'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'ci/cd', 'agile', 'scrum', 
                       'machine learning', 'ai', 'deep learning', 'data science', 'analytics']
    
    for term in technical_terms:
        if term in job_description.lower():
            skills.append(term)
    
    return skills

def enhance_bullet_points_with_ai(resume_bullet_points, job_description):
    """Enhance resume bullet points using AI."""
    try:
        prompt = f"""
        I need to enhance the following resume bullet points to better match this job description:
        
        JOB DESCRIPTION:
        {job_description}
        
        ORIGINAL BULLET POINTS:
        {resume_bullet_points}
        
        Please improve each bullet point by:
        1. Making it more impactful with specific achievements and metrics where possible
        2. Incorporating relevant keywords from the job description
        3. Using action verbs and quantifiable results
        4. Ensuring professional language and clarity
        
        Return the response as a JSON array with the following format for each bullet point:
        [
            {{
                "original": "original bullet point text",
                "enhanced": "enhanced bullet point text"
            }},
            ...
        ]
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert resume writer who helps job seekers optimize their resumes for specific job descriptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1500
        )
        
        # Extract and parse the JSON response
        enhanced_points = json.loads(response.choices[0].message.content)
        return enhanced_points
        
    except Exception as e:
        print(f"Error enhancing bullet points: {str(e)}")
        # Return a simple enhancement as fallback
        return [{"original": point, "enhanced": point} for point in resume_bullet_points]

def analyze_skill_gaps(resume_text, job_description):
    """Analyze skill gaps between resume and job description."""
    try:
        prompt = f"""
        Compare the skills in this resume and job description to identify:
        1. Skills mentioned in the job description but missing or not emphasized in the resume
        2. Strong skills in the resume that match the job description
        
        RESUME:
        {resume_text}
        
        JOB DESCRIPTION:
        {job_description}
        
        Return the analysis as JSON with this format:
        {{
            "missing_skills": ["skill1", "skill2", ...],
            "strong_skills": ["skill1", "skill2", ...]
        }}
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert career advisor who analyzes skill gaps between resumes and job descriptions."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        
        # Extract and parse the JSON response
        skill_analysis = json.loads(response.choices[0].message.content)
        return skill_analysis
        
    except Exception as e:
        print(f"Error analyzing skill gaps: {str(e)}")
        # Return empty analysis as fallback
        return {"missing_skills": [], "strong_skills": []}

def calculate_ats_compatibility_score(resume_text, job_description):
    """Calculate ATS compatibility score based on keyword matching and formatting."""
    try:
        prompt = f"""
        Analyze this resume against the job description to calculate an ATS compatibility score (0-100).
        Consider:
        1. Keyword matching between resume and job description
        2. Presence of required skills and qualifications
        3. Relevant experience alignment
        4. Resume formatting and structure
        
        RESUME:
        {resume_text}
        
        JOB DESCRIPTION:
        {job_description}
        
        Return just a single integer score between 0-100.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert in ATS systems who helps job seekers optimize their resumes."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        
        # Extract the score
        score_text = response.choices[0].message.content.strip()
        # Find the first number in the response
        match = re.search(r'\d+', score_text)
        if match:
            score = int(match.group())
            # Ensure score is in valid range
            score = min(max(score, 0), 100)
            return score
        else:
            return 65  # Default fallback score
        
    except Exception as e:
        print(f"Error calculating ATS score: {str(e)}")
        return 65  # Default fallback score

def extract_matching_keywords(resume_text, job_description):
    """Extract keywords that appear in both the resume and job description."""
    try:
        prompt = f"""
        Identify important keywords that appear in both the resume and job description.
        Focus on technical skills, tools, methodologies, and industry-specific terms.
        
        RESUME:
        {resume_text}
        
        JOB DESCRIPTION:
        {job_description}
        
        Return the response as a JSON array of keywords:
        ["keyword1", "keyword2", ...]
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert in keyword analysis for resume optimization."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=300
        )
        
        # Extract and parse the JSON response
        matching_keywords = json.loads(response.choices[0].message.content)
        return matching_keywords
        
    except Exception as e:
        print(f"Error extracting matching keywords: {str(e)}")
        return []  # Return empty list as fallback

# API Endpoints
@app.post("/api/enhance", response_model=EnhancementResponse)
async def enhance_resume(
    resume_file: UploadFile = File(...),
    job_description: str = Form(...)
):
    """Enhance a resume based on a job description."""
    try:
        # Create a temporary file to store the uploaded resume
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(resume_file.filename)[1]) as temp_file:
            # Write the uploaded file content to the temporary file
            temp_file.write(await resume_file.read())
            temp_file_path = temp_file.name
        
        # Extract text from the resume based on file type
        file_extension = os.path.splitext(resume_file.filename)[1].lower()
        if file_extension == '.pdf':
            resume_text = extract_text_from_pdf(temp_file_path)
        elif file_extension in ['.docx', '.doc']:
            resume_text = extract_text_from_docx(temp_file_path)
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload a PDF or DOCX file.")
        
        # Clean up the temporary file
        os.unlink(temp_file_path)
        
        # Extract bullet points from the resume
        bullet_points = extract_bullet_points(resume_text)
        
        if not bullet_points:
            raise HTTPException(status_code=400, detail="Could not extract bullet points from the resume. Please check the file format.")
        
        # Enhance the bullet points with AI
        enhanced_points = enhance_bullet_points_with_ai(bullet_points, job_description)
        
        # Analyze skill gaps
        skill_analysis = analyze_skill_gaps(resume_text, job_description)
        # Calculate ATS compatibility score
        ats_score = calculate_ats_compatibility_score(resume_text, job_description)
        
        # Extract matching keywords
        matched_keywords = extract_matching_keywords(resume_text, job_description)
        
        # Prepare the response
        response = EnhancementResponse(
            enhanced_bullet_points=enhanced_points,
            missing_skills=skill_analysis.get("missing_skills", []),
            strong_skills=skill_analysis.get("strong_skills", []),
            matched_keywords=matched_keywords,
            ats_score=ats_score
        )
        
        return response
    
    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred while processing the resume.")

# Health check endpoint
@app.get("/")
async def health_check():
    return {"status": "ok", "message": "Resume Enhancement API is running"}

# Run the application
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
