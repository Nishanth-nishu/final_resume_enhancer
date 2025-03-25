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

    // Global variables to store the current resume state
    let currentTailoredResume = "";
    let currentJobDescription = "";
    let currentTemplate = "";
    let currentOutputFormat = "";

    // Debug logging function
    function debugLog(message, data) {
        console.log(`[DEBUG] ${message}`, data);
    }

    // Update the download buttons with proper URLs and visual feedback
    function updateDownloadButtons(pdfUrl, txtUrl) {
        if (pdfUrl) {
            downloadPdfBtn.onclick = function() {
                window.location.href = pdfUrl;
            };
            // Enable the button and update visual cue
            downloadPdfBtn.classList.remove('disabled');
            downloadPdfBtn.setAttribute('title', 'Download updated resume as PDF');
        }
        
        if (txtUrl) {
            downloadTxtBtn.onclick = function() {
                window.location.href = txtUrl;
            };
            // Enable the button and update visual cue
            downloadTxtBtn.classList.remove('disabled');
            downloadTxtBtn.setAttribute('title', 'Download updated resume as text');
        }
        
        // Add visual indicator that download buttons have been updated
        downloadPdfBtn.classList.add('btn-pulse');
        downloadTxtBtn.classList.add('btn-pulse');
        
        // Remove pulse effect after 3 seconds
        setTimeout(() => {
            downloadPdfBtn.classList.remove('btn-pulse');
            downloadTxtBtn.classList.remove('btn-pulse');
        }, 3000);
    }

    // Handle successful tailoring of the resume
    function handleTailorSuccess(data) {
        // Hide loading state
        document.getElementById('loadingCard').style.display = 'none';
        
        // Show the tailored tab
        const tailoredTabItem = document.getElementById('tailored-tab-item');
        tailoredTabItem.style.display = 'block';
        
        // Update tailored text content
        const tailoredResumeText = document.getElementById('tailoredResumeText');
        tailoredResumeText.innerText = data.tailoredResume;
        
        // Switch to tailored tab
        const tailoredTab = document.getElementById('tailored-tab');
        const tabTrigger = new bootstrap.Tab(tailoredTab);
        tabTrigger.show();
        
        // Store the tailored resume
        currentTailoredResume = data.tailoredResume;
        
        // Debug output
        debugLog("PDF URL:", data.pdfUrl);
        debugLog("TXT URL:", data.txtUrl);
        
        // Update download buttons
        updateDownloadButtons(data.pdfUrl, data.txtUrl);
        
        // Update match score
        if (data.matchScore) {
            updateMatchScore(data.matchScore, data.skills || [], data.keywordsUsed || []);
        }
    }

    // Initialize chat functionality
    function initChatInterface() {
        const chatWithResumeBtn = document.getElementById('chatWithResumeBtn');
        const chatCard = document.getElementById('chatCard');
        const sendMessageBtn = document.getElementById('sendMessageBtn');
        const chatInput = document.getElementById('chatInput');
        const chatContainer = document.getElementById('chatContainer');

        // Show chat interface when button is clicked
        chatWithResumeBtn.addEventListener('click', function() {
            chatCard.style.display = 'block';
            chatContainer.scrollTop = chatContainer.scrollHeight;
        });

        // Send message when button is clicked
        sendMessageBtn.addEventListener('click', function() {
            sendChatMessage();
        });

        // Send message when Enter key is pressed
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });

        // Function to send message and get response
        function sendChatMessage() {
            const message = chatInput.value.trim();
            if (!message) return;

            // Display user message
            appendMessage('user', message);
            chatInput.value = '';

            // Show typing indicator
            const typingIndicator = document.createElement('div');
            typingIndicator.className = 'ai-message';
            typingIndicator.id = 'typingIndicator';
            typingIndicator.innerHTML = 'Thinking<span class="typing-dots">...</span>';
            chatContainer.appendChild(typingIndicator);
            chatContainer.scrollTop = chatContainer.scrollHeight;

            // Get the current resume text based on which tab is active
            const tailoredTab = document.getElementById('tailored-tab');
            const enhancedTab = document.getElementById('enhanced-tab');
            
            let currentResumeText;
            if (tailoredTab && tailoredTab.classList.contains('active')) {
                currentResumeText = document.getElementById('tailoredResumeText').innerText;
            } else if (enhancedTab.classList.contains('active')) {
                currentResumeText = document.getElementById('enhancedResumeText').innerText;
            }

            // Send request to the backend
            fetch('/api/chat-with-resume', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    message: message,
                    resumeText: currentResumeText,
                    jobDescription: currentJobDescription,
                    template: currentTemplate,
                    outputFormat: currentOutputFormat
                })
            })
            .then(response => response.json())
            .then(data => {
                // Remove typing indicator
                document.getElementById('typingIndicator').remove();

                if (data.error) {
                    appendMessage('system', `Error: ${data.error}`);
                } else {
                    // Display AI response
                    appendMessage('ai', data.response);
                    
                    // Update resume if modified
                    if (data.updatedResume) {
                        // Store the updated resume
                        currentTailoredResume = data.updatedResume;
                        
                        // Make sure the tailored tab exists
                        const tailoredTabItem = document.getElementById('tailored-tab-item');
                        if (tailoredTabItem) {
                            tailoredTabItem.style.display = 'block';
                        }
                        
                        // Update the content
                        const tailoredResumeText = document.getElementById('tailoredResumeText');
                        tailoredResumeText.innerText = data.updatedResume;
                        
                        // Switch to the tailored tab
                        const tailoredTab = document.getElementById('tailored-tab');
                        if (tailoredTab) {
                            const tabTrigger = new bootstrap.Tab(tailoredTab);
                            tabTrigger.show();
                        }
                        
                        // Update the download buttons to use the new tailored resume
                        updateDownloadButtons(data.pdfUrl, data.txtUrl);
                        
                        // Update match score if provided
                        if (data.matchScore) {
                            updateMatchScore(data.matchScore, data.skills || [], data.keywordsUsed || []);
                        }
                    }
                }
                
                chatContainer.scrollTop = chatContainer.scrollHeight;
            })
            .catch(error => {
                document.getElementById('typingIndicator').remove();
                appendMessage('system', `Error: ${error.message}`);
                chatContainer.scrollTop = chatContainer.scrollHeight;
            });
        }

        // Function to append message to chat container
        function appendMessage(type, message) {
            const messageDiv = document.createElement('div');
            messageDiv.className = type + '-message';
            messageDiv.innerText = message;
            
            // Add timestamp
            const timestamp = document.createElement('div');
            timestamp.className = 'chat-timestamp';
            timestamp.innerText = new Date().toLocaleTimeString();
            messageDiv.appendChild(timestamp);
            
            chatContainer.appendChild(messageDiv);
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }
    }

    // Function to update match score with skills and keywords
    function updateMatchScore(score, skills, keywords) {
        // Show the match score card
        const matchScoreCard = document.getElementById('matchScoreCard');
        matchScoreCard.style.display = 'block';
        
        // Update the progress bar
        const matchScoreBar = document.getElementById('matchScoreBar');
        matchScoreBar.style.width = `${score}%`;
        matchScoreBar.innerText = `${score}%`;
        matchScoreBar.setAttribute('aria-valuenow', score);
        
        // Set color based on score
        if (score >= 80) {
            matchScoreBar.classList.remove('bg-warning', 'bg-danger');
            matchScoreBar.classList.add('bg-success');
        } else if (score >= 60) {
            matchScoreBar.classList.remove('bg-success', 'bg-danger');
            matchScoreBar.classList.add('bg-warning');
        } else {
            matchScoreBar.classList.remove('bg-success', 'bg-warning');
            matchScoreBar.classList.add('bg-danger');
        }
        
        // Update skills list
        const skillsList = document.getElementById('skillsList');
        skillsList.innerHTML = '';
        skills.forEach(skill => {
            const badge = document.createElement('span');
            badge.className = 'badge bg-primary';
            badge.innerText = skill;
            skillsList.appendChild(badge);
        });
        
        // Update keywords list
        const keywordsList = document.getElementById('keywordsList');
        keywordsList.innerHTML = '';
        keywords.forEach(keyword => {
            const badge = document.createElement('span');
            badge.className = 'badge bg-secondary';
            badge.innerText = keyword;
            keywordsList.appendChild(badge);
        });
    }

    // Initialize chat interface
    initChatInterface();
    
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
        updateMatchScore(data.matchScore, data.skills, data.keywordsUsed);
        
        // Update skills and keywords
        displaySkillsAndKeywords(data.skills, data.keywordsUsed);
        
        // Hide tailored tab if not yet generated
        tailoredTabItem.style.display = 'none';
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
            updateMatchScore(data.matchScore, data.skills, data.keywordsUsed);
            
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

    // Debug initialization
    function debug_init() {
        // Add click event listeners to document to track actual clicks
        document.addEventListener('click', function(e) {
            if (e.target.id === 'downloadPdfBtn' || e.target.closest('#downloadPdfBtn')) {
                debugLog("Download PDF button clicked");
            }
            if (e.target.id === 'downloadTxtBtn' || e.target.closest('#downloadTxtBtn')) {
                debugLog("Download TXT button clicked");
            }
        });
    }

    // Call debug initialization
    debug_init();
});