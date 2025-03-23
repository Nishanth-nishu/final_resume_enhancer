// Main JavaScript for the AI Resume Enhancer

document.addEventListener('DOMContentLoaded', function() {
    // Cache DOM elements
    const resumeForm = document.getElementById('resumeForm');
    const enhanceBtn = document.getElementById('enhanceBtn');
    const loadingCard = document.getElementById('loadingCard');
    const resultsContainer = document.getElementById('resultsContainer');
    const errorCard = document.getElementById('errorCard');
    const matchScoreCard = document.getElementById('matchScoreCard');
    const tryAgainBtn = document.getElementById('tryAgainBtn');
    const tailorMoreBtn = document.getElementById('tailorMoreBtn');
    
    // Results tabs and content
    const originalResumeText = document.getElementById('originalResumeText');
    const enhancedResumeText = document.getElementById('enhancedResumeText');
    const tailoredResumeText = document.getElementById('tailoredResumeText');
    const tailoredTabItem = document.getElementById('tailored-tab-item');
    
    // Download buttons
    const downloadPdfBtn = document.getElementById('downloadPdfBtn');
    const downloadTxtBtn = document.getElementById('downloadTxtBtn');
    
    // Match score and keywords
    const matchScoreBar = document.getElementById('matchScoreBar');
    const skillsList = document.getElementById('skillsList');
    const keywordsList = document.getElementById('keywordsList');
    
    // Store data from API responses
    let currentResume = {
        original: '',
        enhanced: '',
        tailored: '',
        pdfUrl: '',
        txtUrl: '',
        tailoredPdfUrl: '',
        tailoredTxtUrl: '',
        jobDescription: '',
        template: '',
        outputFormat: ''
    };
    
    // Handle form submission
    resumeForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        // Show loading, hide results and error
        loadingCard.style.display = 'block';
        resultsContainer.style.display = 'none';
        errorCard.style.display = 'none';
        matchScoreCard.style.display = 'none';
        
        // Get form data
        const formData = new FormData(resumeForm);
        
        // Store values for later use
        currentResume.jobDescription = formData.get('jobDescription');
        currentResume.template = formData.get('template');
        currentResume.outputFormat = formData.get('outputFormat');
        
        // Disable the submit button while processing
        enhanceBtn.disabled = true;
        enhanceBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processing...';
        
        // Call the API
        fetch('/api/enhance-resume', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'An error occurred while enhancing your resume');
                });
            }
            return response.json();
        })
        .then(data => {
            // Store the results
            currentResume.original = data.originalResume;
            currentResume.enhanced = data.enhancedResume;
            currentResume.pdfUrl = data.pdfUrl;
            currentResume.txtUrl = data.txtUrl;
            
            // Display the results
            displayResults(data);
            
            // Hide loading, show results
            loadingCard.style.display = 'none';
            resultsContainer.style.display = 'block';
            matchScoreCard.style.display = 'block';
            
            // Reset button
            enhanceBtn.disabled = false;
            enhanceBtn.innerHTML = '<i class="bi bi-magic"></i> Enhance Resume';
        })
        .catch(error => {
            console.error('Error:', error);
            
            // Show error message
            document.getElementById('errorMessage').textContent = error.message;
            
            // Hide loading, show error
            loadingCard.style.display = 'none';
            errorCard.style.display = 'block';
            
            // Reset button
            enhanceBtn.disabled = false;
            enhanceBtn.innerHTML = '<i class="bi bi-magic"></i> Enhance Resume';
        });
    });
    
    // Display the results in the UI
    function displayResults(data) {
        // Set the resume text
        originalResumeText.textContent = data.originalResume;
        enhancedResumeText.textContent = data.enhancedResume;
        
        // Set download URLs
        downloadPdfBtn.onclick = function() {
            window.open(data.pdfUrl, '_blank');
        };
        
        downloadTxtBtn.onclick = function() {
            window.open(data.txtUrl, '_blank');
        };
        
        // Update match score
        updateMatchScore(data.matchScore);
        
        // Update skills and keywords
        displaySkillsAndKeywords(data.skills, data.keywordsUsed);
        
        // Hide tailored tab if not yet generated
        tailoredTabItem.style.display = 'none';
    }
    
    // Update the match score progress bar
    function updateMatchScore(score) {
        const scoreValue = parseInt(score);
        matchScoreBar.style.width = scoreValue + '%';
        matchScoreBar.setAttribute('aria-valuenow', scoreValue);
        matchScoreBar.textContent = scoreValue + '%';
        
        // Set color based on score
        if (scoreValue < 50) {
            matchScoreBar.classList.remove('bg-success', 'bg-warning', 'bg-primary');
            matchScoreBar.classList.add('bg-danger');
        } else if (scoreValue < 70) {
            matchScoreBar.classList.remove('bg-success', 'bg-danger', 'bg-primary');
            matchScoreBar.classList.add('bg-warning');
        } else if (scoreValue < 85) {
            matchScoreBar.classList.remove('bg-danger', 'bg-warning', 'bg-success');
            matchScoreBar.classList.add('bg-primary');
        } else {
            matchScoreBar.classList.remove('bg-danger', 'bg-warning', 'bg-primary');
            matchScoreBar.classList.add('bg-success');
        }
    }
    
    // Display skills and keywords used
    function displaySkillsAndKeywords(skills, keywords) {
        // Clear previous lists
        skillsList.innerHTML = '';
        keywordsList.innerHTML = '';
        
        // Add skills
        if (skills && skills.length > 0) {
            skills.forEach(skill => {
                const skillBadge = document.createElement('span');
                skillBadge.className = 'tag skill-badge';
                skillBadge.textContent = skill;
                skillsList.appendChild(skillBadge);
            });
        } else {
            skillsList.innerHTML = '<p class="text-muted">No skills detected</p>';
        }
        
        // Add keywords
        if (keywords && keywords.length > 0) {
            keywords.forEach(keyword => {
                const keywordBadge = document.createElement('span');
                keywordBadge.className = 'tag keyword-badge';
                keywordBadge.textContent = keyword;
                keywordsList.appendChild(keywordBadge);
            });
        } else {
            keywordsList.innerHTML = '<p class="text-muted">No keywords detected</p>';
        }
    }
    
    // Try again button handler
    tryAgainBtn.addEventListener('click', function() {
        errorCard.style.display = 'none';
    });
    
    // Further tailor button handler
    tailorMoreBtn.addEventListener('click', function() {
        // Disable the button while processing
        tailorMoreBtn.disabled = true;
        tailorMoreBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Tailoring...';
        
        // Show loading
        loadingCard.style.display = 'block';
        resultsContainer.style.display = 'none';
        
        // Create request data
        const requestData = {
            enhancedResume: currentResume.enhanced,
            jobDescription: currentResume.jobDescription,
            template: currentResume.template,
            outputFormat: currentResume.outputFormat
        };
        
        // Call the API to tailor the resume
        fetch('/api/download-tailored', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        })
        .then(response => {
            if (!response.ok) {
                return response.json().then(data => {
                    throw new Error(data.error || 'An error occurred while tailoring your resume');
                });
            }
            return response.json();
        })
        .then(data => {
            // Store the tailored resume
            currentResume.tailored = data.tailoredResume;
            currentResume.tailoredPdfUrl = data.pdfUrl;
            currentResume.tailoredTxtUrl = data.txtUrl;
            
            // Display the tailored resume
            tailoredResumeText.textContent = data.tailoredResume;
            
            // Show the tailored tab
            tailoredTabItem.style.display = 'block';
            document.getElementById('tailored-tab').click();
            
            // Update download buttons to use tailored version
            downloadPdfBtn.onclick = function() {
                window.open(data.pdfUrl, '_blank');
            };
            
            downloadTxtBtn.onclick = function() {
                window.open(data.txtUrl, '_blank');
            };
            
            // Update match score and keywords
            updateMatchScore(data.matchScore);
            displaySkillsAndKeywords(data.skills, data.keywordsUsed);
            
            // Hide loading, show results
            loadingCard.style.display = 'none';
            resultsContainer.style.display = 'block';
            
            // Reset button
            tailorMoreBtn.disabled = false;
            tailorMoreBtn.innerHTML = '<i class="bi bi-bullseye"></i> Further Tailor for This Job';
        })
        .catch(error => {
            console.error('Error:', error);
            
            // Show error message
            document.getElementById('errorMessage').textContent = error.message;
            
            // Hide loading, show error
            loadingCard.style.display = 'none';
            errorCard.style.display = 'block';
            
            // Reset button
            tailorMoreBtn.disabled = false;
            tailorMoreBtn.innerHTML = '<i class="bi bi-bullseye"></i> Further Tailor for This Job';
        });
    });
    
    // Handle file input max size validation
    const resumeFile = document.getElementById('resumeFile');
    resumeFile.addEventListener('change', function() {
        const fileSize = this.files[0]?.size || 0;
        const maxSize = 10 * 1024 * 1024; // 10MB
        
        if (fileSize > maxSize) {
            alert('File size exceeds 10MB limit. Please choose a smaller file.');
            this.value = ''; // Clear the file input
        }
    });
});