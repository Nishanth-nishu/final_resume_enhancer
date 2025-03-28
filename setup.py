from setuptools import setup, find_packages

setup(
    name="AI resume_enhancer",
    version="1.0.0",
    description="A Flask application for enhancing resumes using Google's Gemini AI",
    long_description="""This application provides a web interface for users to upload their resumes,
    get them enhanced with AI based on a job description, and download professionally formatted versions.""",
    author="R Nishanth",
    author_email="rnishanth2317@gmail.com",
    url="https://github.com/Nishanth-nishu/final_resume_enhancer.git",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "flask>=2.0.0",
        "google-generativeai>=0.3.0",
        "python-dotenv>=0.19.0",
        "PyPDF2>=2.0.0",
        "pdfminer.six>=20211012",
        "python-docx>=0.8.10",
        "striprtf>=0.0.10",
        "fpdf2>=2.5.5",
        "pillow>=9.0.0",
        "requests>=2.26.0",
        "werkzeug>=2.0.0",
        "uuid>=1.30.0",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "pytest-cov>=2.0.0",
            "flake8>=3.9.0",
            "black>=21.0",
            "isort>=5.0.0",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Flask",
        "Intended Audience :: End Users/Desktop",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Office/Business",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
    ],
    python_requires=">=3.8",
    entry_points={
        "console_scripts": [
            "resume-enhancer=app:main",
        ],
    },
    keywords="resume enhancement AI gemini flask",
    project_urls={
        "Bug Reports": "https://github.com/Nishanth-nishu/final_resume_enhancer.git/issues",
        "Source": "https://github.com/Nishanth-nishu/final_resume_enhancer.git",
    },
)