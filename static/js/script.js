// Get DOM elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('resume-upload');
const fileNameDisplay = document.getElementById('file-name');

// Add event listeners for drag-and-drop
dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
});

dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
});

dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');

    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        updateFileName(files[0].name);
    }
});

// Add event listener for file input change
fileInput.addEventListener('change', (e) => {
    const files = e.target.files;
    if (files.length > 0) {
        updateFileName(files[0].name);
    }
});

// Update file name display
function updateFileName(fileName) {
    fileNameDisplay.textContent = fileName;
    document.getElementById('upload-status').classList.remove('hidden');
}

// Enhance resume button click handler
document.getElementById('enhance-resume').addEventListener('click', async () => {
    const formData = new FormData();
    const resumeFile = fileInput.files[0];
    const jobDescription = document.getElementById('job-description').value;
    const template = document.getElementById('resume-template').value;

    if (!resumeFile) {
        alert("Please upload a resume file.");
        return;
    }

    if (!jobDescription) {
        alert("Please enter a job description.");
        return;
    }

    formData.append('resume', resumeFile);
    formData.append('jobDescription', jobDescription);
    formData.append('template', template);

    // Show loading spinner (if you have one)
    document.getElementById('loading-spinner').classList.remove('hidden');

    try {
        const response = await fetch('/api/enhance-resume', {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            throw new Error(`HTTP error! Status: ${response.status}`);
        }

        const data = await response.json();

        // Hide loading spinner and show results
        document.getElementById('loading-spinner').classList.add('hidden');
        document.getElementById('results-preview').classList.remove('hidden');
        document.getElementById('before-resume').innerText = data.originalResume;
        document.getElementById('after-resume').innerText = data.enhancedResume;
        document.getElementById('download-link').href = data.pdfUrl;
    } catch (error) {
        console.error('Error:', error);
        alert('An error occurred while enhancing your resume. Please try again.');
    }
});