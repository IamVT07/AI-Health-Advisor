// --- 1. MAIN FUNCTION TO GET ADVICE ---
async function getAdvice() {
    const symptomsInput = document.getElementById('symptoms');
    const symptoms = symptomsInput.value;

    // Validation
    if (!symptoms.trim()) {
        alert("Please enter your symptoms first.");
        return;
    }

    // Show loading state
    const adviceText = document.getElementById('advice');
    const conditionsList = document.getElementById('conditions');
    adviceText.textContent = "Consulting AI Doctor... Please wait.";
    conditionsList.innerHTML = ""; // Clear previous results

    try {
        // Send data to Python (main.py)
        const response = await fetch('/get_advice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symptoms: symptoms })
        });

        if (!response.ok) {
            throw new Error("Server error");
        }

        const data = await response.json();
        
        // Render the results on screen
        renderResults(data);

        // Check for severe warning
        if (data.see_doctor) {
            alert("⚠️ Warning: Your symptoms indicate a serious condition. Please see a doctor immediately.");
        }

    } catch (error) {
        console.error("Error:", error);
        adviceText.textContent = "Error: Could not connect to the Health System. Please ensure 'main.py' is running.";
    }
}

// --- 2. FUNCTION TO DISPLAY RESULTS ---
function renderResults(data) {
    const conditionsList = document.getElementById('conditions');
    const adviceText = document.getElementById('advice');
    const outputSection = document.querySelector('.output-section');
    
    // 1. यूजर ने क्या लिखा था, उसे भी निकालो (New Addition)
    const userSymptoms = document.getElementById('symptoms').value;

    // Clear previous list
    conditionsList.innerHTML = "";

    // --- NEW: Add Symptoms to the top of the report ---
    // हम एक नया Header जोड़ रहे हैं जो बताया कि मरीज ने क्या कहा था
    const symptomHeader = document.createElement('div');
    symptomHeader.innerHTML = `
        <p style="border-bottom: 1px solid #555; padding-bottom: 5px; margin-bottom: 10px;">
            <strong style="color: #ff4b4b;">Patient's Complaint (Symptoms):</strong><br>
            <span style="color: white; font-size: 1.1em;">"${userSymptoms}"</span>
        </p>
    `;
    conditionsList.appendChild(symptomHeader);
    // --------------------------------------------------

    // A. Show Conditions List (AI Diagnosis)
    if (data.conditions && data.conditions.length > 0) {
        data.conditions.forEach(item => {
            const li = document.createElement('li');
            li.innerHTML = `
                <strong>Diagnosis: ${item.name}</strong><br>
                <span class="cond-cause">Cause: ${item.cause}</span><br>
                <span class="cond-solution">Remedy: ${item.solution}</span>
            `;
            conditionsList.appendChild(li);
        });
    } else {
        const li = document.createElement('li');
        li.innerHTML = "No specific condition identified based on your input.";
        conditionsList.appendChild(li);
    }

    // B. Show General Advice
    adviceText.textContent = data.advice || "Take care of your health.";

    // C. Make the result section visible
    if (outputSection) {
        outputSection.classList.add('output-visible');
    }

   // --- NEW: AUTO SPEAK CODE ---
    // सलाह को बोलने लायक टेक्स्ट में बदलो
    if (data.conditions && data.conditions.length > 0) {
        const textToSpeak = `Diagnosis: ${data.conditions[0].name}. Advice: ${data.advice}`;
        speakText(textToSpeak);
    } else {
        speakText(data.advice);
    }
}

// --- 3. TEXT-TO-SPEECH HELPERS ---

// Create a readable string for the AI to speak
function buildSpeakTextFromData(data) {
    const lang = document.getElementById('langSelect').value || 'en-US';
    const isHindi = lang.startsWith('hi');

    if (!data || !data.conditions || data.conditions.length === 0) {
        return isHindi 
            ? 'क्षमा करें, मुझे आपकी बीमारी समझ नहीं आई। कृपया डॉक्टर से मिलें।' 
            : 'I could not identify the condition. Please consult a doctor.';
    }

    const lines = [];
    
    // Intro
    lines.push(isHindi ? "विश्लेषण के आधार पर:" : "Based on your symptoms:");

    // Loop through conditions
    data.conditions.forEach((c) => {
        if (isHindi) {
            lines.push(`संभावित बीमारी है: ${c.name}`);
            lines.push(`इसका कारण है: ${c.cause}`);
            lines.push(`घरेलू उपाय: ${c.solution}`);
        } else {
            lines.push(`Possible condition is: ${c.name}`);
            lines.push(`Cause: ${c.cause}`);
            lines.push(`Remedy: ${c.solution}`);
        }
    });

    // General Advice
    lines.push(isHindi ? "सलाह: " + data.advice : "Advice: " + data.advice);

    return lines.join('. ');
}

// Function to actually speak
function speakText(text) {
    if (!window.speechSynthesis) {
        console.warn("Text-to-speech not supported.");
        return;
    }
    
    // Stop any previous speech
    window.speechSynthesis.cancel();

    const utter = new SpeechSynthesisUtterance(text);
    const langSelect = document.getElementById('langSelect');
   // अगर टेक्स्ट में हिंदी अक्षर हैं या 'Bukhar' जैसा कुछ है, तो हिंदी में बोलो
utter.lang = 'hi-IN'; 
// (या अगर आप चाहते हैं कि यूजर खुद चुने तो dropdown वाला कोड रहने दें)

    window.speechSynthesis.speak(utter);
}

// Button Event Listener for "Read Advice" button
const speakAdviceBtn = document.getElementById('speakAdviceBtn');
if (speakAdviceBtn) {
    speakAdviceBtn.addEventListener('click', () => {
        const advice = document.getElementById('advice').textContent;
        if (advice) speakText(advice);
    });
}

// --- 4. SPEECH RECOGNITION (Mic Button) ---
const micBtn = document.getElementById('micBtn');
let recognition = null;

if (micBtn) {
    // Check browser support
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

    if (SpeechRecognition) {
        recognition = new SpeechRecognition();
        recognition.continuous = false;
        recognition.interimResults = false;

        micBtn.addEventListener('click', () => {
            const lang = document.getElementById('langSelect').value || 'en-US';
            recognition.lang = lang;
            
            try {
                recognition.start();
                micBtn.classList.add('listening'); // Add CSS class for animation if you have one
                micBtn.style.backgroundColor = "red"; // Visual feedback
            } catch (e) {
                console.log("Mic already active");
            }
        });

        recognition.onresult = (event) => {
            const transcript = event.results[0][0].transcript;
            document.getElementById('symptoms').value = transcript;
            // Auto-submit after speaking (Optional)
            // getAdvice(); 
        };

        recognition.onend = () => {
            micBtn.classList.remove('listening');
            micBtn.style.backgroundColor = ""; // Reset color
        };
    } else {
        micBtn.style.display = 'none'; // Hide mic if not supported
        console.warn("Speech Recognition not supported in this browser.");
    }
}
// --- PDF DOWNLOAD FUNCTION ---
function downloadPDF() {
    const outputDiv = document.querySelector('.output-section');
    
    // आज की तारीख डालना (ताकि PDF में डेट दिखे)
    const today = new Date().toLocaleDateString();
    outputDiv.setAttribute('data-date', today);

    // प्रिंट कमांड (Browser का अपना PDF Maker)
    window.print();
}