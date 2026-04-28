import os
import smtplib
from dotenv import load_dotenv
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_cors import CORS
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
from deep_translator import GoogleTranslator

# --- 1. SETUP ---
load_dotenv()  # Load environment variables from .env file
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__,
            template_folder=os.path.join(basedir, 'templates'),
            static_folder=os.path.join(basedir, 'static'))
CORS(app)

app.config['SECRET_KEY'] = os.environ.get("SECRET_KEY")

# --- MONGODB CONNECTION ---
# Change this URI to your MongoDB connection string if using Atlas:
# e.g. "mongodb+srv://<user>:<pass>@cluster.mongodb.net/health_app"
MONGO_URI =os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client["health_app"]

# Collections (equivalent to tables)
users_col       = db["users"]
doctors_col     = db["doctors"]
appointments_col = db["appointments"]
health_logs_col = db["health_logs"]
weight_logs_col = db["weight_logs"]

# --- EMAIL CONFIGURATION ---
SMTP_SERVER   = "smtp.gmail.com"
SMTP_PORT     = 587
SENDER_EMAIL  = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")

def send_doctor_alert(doctor_name, patient_name, date, to_email, appt_id, doctor_id):
    try:
        subject = f"New Appointment Request: {patient_name}"
        dashboard_url = f"http://127.0.0.1:5000/login?next=/doctor_panel/{doctor_id}"
        body = f"""
        <html><body style="font-family: Arial, sans-serif;">
            <h2>Hello {doctor_name},</h2>
            <p>You have a new appointment request!</p>
            <div style="background:#f4f4f4;padding:15px;border-radius:5px;">
                <p><strong>Patient:</strong> {patient_name}</p>
                <p><strong>Date:</strong> {date}</p>
                <p><strong>Reason:</strong> Checkup</p>
            </div><br>
            <p>Please login to your <b>Doctor Panel</b> to Accept or Reject.</p>
            <a href="{dashboard_url}" style="background-color:#3498db;color:white;padding:10px 20px;
               text-decoration:none;border-radius:5px;">Login to Dashboard</a>
        </body></html>
        """
        msg = MIMEText(body, 'html')
        msg['Subject'] = subject
        msg['From']    = SENDER_EMAIL
        msg['To']      = to_email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"❌ Email sending failed: {e}")


# --- 2. USER CLASS FOR FLASK-LOGIN ---
class User(UserMixin):
    """Wraps a MongoDB user document for Flask-Login."""
    def __init__(self, doc):
        self._doc = doc

    # Flask-Login needs a string ID
    def get_id(self):
        return str(self._doc["_id"])

    # Expose document fields as attributes
    def __getattr__(self, name):
        try:
            return self._doc[name]
        except KeyError:
            raise AttributeError(name)

    @property
    def id(self):
        return str(self._doc["_id"])

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False


# --- 3. LOGIN MANAGER ---
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    try:
        doc = users_col.find_one({"_id": ObjectId(user_id)})
        return User(doc) if doc else None
    except Exception:
        return None


# --- 4. MEDICAL DATA (unchanged) ---
MEDICAL_DATA = [
    {"keywords": ["fever","bukhar","temperature","garam","बुखार"],
     "condition": "Viral Fever (वायरल बुखार)",
     "cause": "Viral infection or weather change. (मौसम में बदलाव)",
     "remedy": "Take rest, drink plenty of water & take Paracetamol. (आराम करें, खूब पानी पिएं और पैरासिटामोल लें।)",
     "severe": False},
    {"keywords": ["headache","sir dard","sar dard","tension","migraine","सिर दर्द"],
     "condition": "Headache (सिर दर्द)",
     "cause": "Stress, lack of sleep or dehydration. (तनाव या नींद की कमी)",
     "remedy": "Sleep in a dark room, drink water. (अंधेरे कमरे में सोएं और पानी पिएं।)",
     "severe": False},
    {"keywords": ["cold","cough","sardi","khasi","zukam","runny nose","जुकाम"],
     "condition": "Common Cold (सर्दी-जुकाम)",
     "cause": "Viral infection. (वायरल इन्फेक्शन)",
     "remedy": "Steam inhalation, ginger tea, gargle. (भाप लें और अदरक वाली चाय पिएं।)",
     "severe": False},
    {"keywords": ["stomach","pet dard","gas","acidity","indigestion","पेट दर्द"],
     "condition": "Stomach Ache (पेट दर्द/गैस)",
     "cause": "Spicy food or irregular eating. (मसालेदार खाना)",
     "remedy": "Drink lemon water, eat curd-rice, avoid oily food. (नींबू पानी पिएं और हल्का खाना खाएं।)",
     "severe": False},
    {"keywords": ["vomit","ulti","nausea","food poisoning","उल्टी"],
     "condition": "Food Poisoning (फूड पॉइजनिंग)",
     "cause": "Contaminated food. (खराब खाना)",
     "remedy": "Drink ORS or electrolytes slowly. (ORS का घोल पिएं।)",
     "severe": True},
    {"keywords": ["diarrhea","loose motion","dast","pait kharab","दस्त"],
     "condition": "Diarrhea (दस्त)",
     "cause": "Contaminated water or food infection. (दूषित पानी या खाना)",
     "remedy": "Drink ORS, eat banana & boiled rice. Avoid dairy. (ORS पिएं, केला और उबला चावल खाएं।)",
     "severe": True},
    {"keywords": ["constipation","kabz","hard stool","pet saaf nahi","कब्ज"],
     "condition": "Constipation (कब्ज)",
     "cause": "Low fiber diet or dehydration. (कम रेशेदार खाना या पानी की कमी)",
     "remedy": "Drink warm water, eat papaya and high-fiber foods. (गर्म पानी पिएं और पपीता खाएं।)",
     "severe": False},
    {"keywords": ["back pain","kamar dard","peeth dard","spine","कमर दर्द"],
     "condition": "Back Pain (कमर दर्द)",
     "cause": "Poor posture, muscle strain or lifting heavy weights. (गलत बैठने की मुद्रा या भारी वजन उठाना)",
     "remedy": "Rest, hot compress, light stretching. Avoid bending suddenly. (आराम करें और गर्म सिकाई करें।)",
     "severe": False},
    {"keywords": ["toothache","daant dard","dental","molar pain","दाँत दर्द"],
     "condition": "Toothache (दाँत दर्द)",
     "cause": "Tooth decay or gum infection. (दाँत में सड़न या मसूड़ों का इन्फेक्शन)",
     "remedy": "Clove oil on affected area. See a dentist soon. (लौंग का तेल लगाएं और दंत चिकित्सक से मिलें।)",
     "severe": False},
    {"keywords": ["eye pain","aankh dard","red eye","conjunctivitis","aankhon mein jalan","आँख दर्द"],
     "condition": "Eye Irritation / Conjunctivitis (आँख का इन्फेक्शन)",
     "cause": "Bacterial or viral infection, dust or allergies. (धूल या इन्फेक्शन)",
     "remedy": "Wash eyes with clean water, use rose water drops, avoid touching eyes. (साफ पानी से आँखें धोएं।)",
     "severe": False},
    {"keywords": ["ear pain","kaan dard","ear infection","bahra","कान दर्द"],
     "condition": "Ear Pain (कान दर्द)",
     "cause": "Ear infection or fluid build-up. (कान में इन्फेक्शन या पानी जमा होना)",
     "remedy": "Warm compress on ear, avoid inserting objects. Consult doctor if severe. (गर्म सिकाई करें।)",
     "severe": False},
    {"keywords": ["skin rash","kharish","khujli","allergy","itching","daane","खुजली"],
     "condition": "Skin Rash / Allergy (त्वचा पर दाने/खुजली)",
     "cause": "Allergic reaction, heat, or insect bite. (एलर्जी या गर्मी)",
     "remedy": "Apply calamine lotion, avoid scratching. Take antihistamine. (कैलामाइन लोशन लगाएं।)",
     "severe": False},
    {"keywords": ["diabetes","sugar","madhumeh","blood sugar high","मधुमेह"],
     "condition": "Diabetes (मधुमेह/शुगर)",
     "cause": "Insulin deficiency or insulin resistance. (इंसुलिन की कमी)",
     "remedy": "Control sugar intake, exercise daily, take prescribed medicine. (मीठा कम खाएं और डॉक्टर की दवा लें।)",
     "severe": True},
    {"keywords": ["hypertension","blood pressure","high bp","BP high","uchch raktachap","उच्च रक्तचाप"],
     "condition": "High Blood Pressure (उच्च रक्तचाप)",
     "cause": "Stress, excess salt or genetic factors. (तनाव, ज्यादा नमक या वंशानुगत कारण)",
     "remedy": "Reduce salt, walk 30 min daily, take prescribed medication. (नमक कम करें और नियमित व्यायाम करें।)",
     "severe": True},
    {"keywords": ["low bp","low blood pressure","chakkar","dizziness","fainting","behoshi","चक्कर"],
     "condition": "Low Blood Pressure (निम्न रक्तचाप)",
     "cause": "Dehydration, low salt or prolonged standing. (पानी की कमी या लंबे समय तक खड़े रहना)",
     "remedy": "Drink ORS or lemon-salt water, lie down and rest. (नमक-चीनी का पानी पिएं और लेट जाएं।)",
     "severe": True},
    {"keywords": ["asthma","saans","breathlessness","wheezing","dam","दमा"],
     "condition": "Asthma (दमा/अस्थमा)",
     "cause": "Dust, pollution, allergies or cold air. (धूल, प्रदूषण या ठंडी हवा)",
     "remedy": "Use inhaler, avoid triggers, stay away from smoke. (इनहेलर का उपयोग करें और धुएँ से दूर रहें।)",
     "severe": True},
    {"keywords": ["typhoid","enteric fever","maiyaad bukhar","typhoid fever","टायफाइड"],
     "condition": "Typhoid (टायफाइड)",
     "cause": "Contaminated food or water (Salmonella bacteria). (दूषित पानी या खाना)",
     "remedy": "See a doctor immediately. Take antibiotics only as prescribed. Stay hydrated. (तुरंत डॉक्टर से मिलें।)",
     "severe": True},
    {"keywords": ["malaria","malarial fever","thanda bukhar","mosquito fever","मलेरिया"],
     "condition": "Malaria (मलेरिया)",
     "cause": "Anopheles mosquito bite. (मच्छर के काटने से)",
     "remedy": "See doctor urgently. Use mosquito nets and repellent. (तुरंत डॉक्टर से मिलें और मच्छरदानी का उपयोग करें।)",
     "severe": True},
    {"keywords": ["dengue","dengue fever","platelet","हड्डी बुखार"],
     "condition": "Dengue Fever (डेंगू बुखार)",
     "cause": "Aedes mosquito bite. (एडीज मच्छर के काटने से)",
     "remedy": "Urgent hospitalization if platelets drop. Drink papaya leaf juice. (डॉक्टर को तुरंत दिखाएं।)",
     "severe": True},
    {"keywords": ["jaundice","peela","piliya","liver","eyes yellow","पीलिया"],
     "condition": "Jaundice (पीलिया)",
     "cause": "Liver infection or bile duct blockage. (लिवर का इन्फेक्शन)",
     "remedy": "Rest, drink sugarcane juice, eat light food. Avoid oily food. (गन्ने का रस पिएं और हल्का खाना खाएं।)",
     "severe": True},
    {"keywords": ["kidney stone","pathri","patthar","renal stone","पथरी"],
     "condition": "Kidney Stone (गुर्दे की पथरी)",
     "cause": "Lack of water, excess calcium or oxalate. (पानी की कमी या अधिक कैल्शियम)",
     "remedy": "Drink 3-4 liters of water daily. See urologist for large stones. (खूब पानी पिएं और डॉक्टर से मिलें।)",
     "severe": True},
    {"keywords": ["anemia","khoon ki kami","hemoglobin low","weakness","paleness","खून की कमी"],
     "condition": "Anemia (रक्त की कमी/एनीमिया)",
     "cause": "Iron or B12 deficiency. (आयरन या B12 की कमी)",
     "remedy": "Eat spinach, dates, lentils and take iron supplements. (पालक, खजूर और दाल खाएं।)",
     "severe": False},
    {"keywords": ["thyroid","weight gain","weight loss","fatigue","थायराइड"],
     "condition": "Thyroid Disorder (थायराइड रोग)",
     "cause": "Hormonal imbalance of thyroid gland. (थायराइड ग्रंथि का असंतुलन)",
     "remedy": "Get TSH test done. Take prescribed medication daily without missing doses. (डॉक्टर से TSH टेस्ट करवाएं।)",
     "severe": True},
    {"keywords": ["chicken pox","chechak","varicella","pox","smallpox","चेचक"],
     "condition": "Chickenpox (छोटी माता/चेचक)",
     "cause": "Varicella-zoster virus. (वेरिसेला वायरस)",
     "remedy": "Calamine lotion on blisters, neem leaves bath. Isolate patient. (नीम के पानी से नहाएं और अलग रहें।)",
     "severe": False},
    {"keywords": ["measles","khasra","rash fever","खसरा"],
     "condition": "Measles (खसरा)",
     "cause": "Rubeola virus spread by air. (हवा से फैलने वाला वायरस)",
     "remedy": "Rest, fluids, vitamin A supplements. Consult doctor for complications. (डॉक्टर से मिलें और आराम करें।)",
     "severe": True},
    {"keywords": ["mumps","galphara","swollen gland","गलसुआ"],
     "condition": "Mumps (गलसुआ)",
     "cause": "Mumps virus affecting salivary glands. (ममप्स वायरस)",
     "remedy": "Cold compress on swollen area, soft foods, rest. Consult doctor. (ठंडी सिकाई करें और नरम खाना खाएं।)",
     "severe": False},
    {"keywords": ["tuberculosis","TB","kshay rog","lungs cough blood","क्षय रोग"],
     "condition": "Tuberculosis - TB (क्षय रोग/टी.बी.)",
     "cause": "Mycobacterium tuberculosis bacteria. (माइकोबैक्टीरियम बैक्टीरिया)",
     "remedy": "See doctor immediately. Complete DOTS treatment. Do not skip doses. (तुरंत डॉक्टर से मिलें और दवा पूरी करें।)",
     "severe": True},
    {"keywords": ["scabies","khaj","mange","skin mites","खाज"],
     "condition": "Scabies (खाज/खुजली)",
     "cause": "Mite infestation of skin. (त्वचा में घुन का प्रकोप)",
     "remedy": "Apply permethrin cream all over body. Wash all clothes & bedding. (परमेथ्रिन क्रीम लगाएं और कपड़े धोएं।)",
     "severe": False},
    {"keywords": ["ringworm","daad","fungal infection","tinea","दाद"],
     "condition": "Ringworm / Fungal Infection (दाद)",
     "cause": "Fungal infection on skin. (त्वचा पर फंगल इन्फेक्शन)",
     "remedy": "Apply antifungal cream (clotrimazole). Keep area dry and clean. (एंटीफंगल क्रीम लगाएं और सूखा रखें।)",
     "severe": False},
    {"keywords": ["piles","hemorrhoids","bawaseer","bleeding stool","बवासीर"],
     "condition": "Piles / Hemorrhoids (बवासीर)",
     "cause": "Constipation, low fiber diet or straining. (कब्ज और कम रेशे वाला खाना)",
     "remedy": "Eat high-fiber food, drink lots of water, use sitz bath. (ज्यादा पानी पिएं और रेशेदार खाना खाएं।)",
     "severe": False},
    {"keywords": ["UTI","urinary infection","peshaab mein jalan","burning urination","मूत्र संक्रमण"],
     "condition": "Urinary Tract Infection - UTI (मूत्र संक्रमण)",
     "cause": "Bacterial infection in urinary tract. (बैक्टीरिया का संक्रमण)",
     "remedy": "Drink plenty of water, cranberry juice. See doctor for antibiotics. (खूब पानी पिएं और डॉक्टर से दवा लें।)",
     "severe": True},
    {"keywords": ["joint pain","arthritis","gathiya","ghutna dard","jodo ka dard","जोड़ों का दर्द"],
     "condition": "Arthritis / Joint Pain (जोड़ों का दर्द/गठिया)",
     "cause": "Wear and tear of joints, uric acid build-up or autoimmune. (जोड़ों की टूट-फूट या यूरिक एसिड)",
     "remedy": "Warm compress, gentle exercise, anti-inflammatory diet. Consult doctor. (गर्म सिकाई और हल्का व्यायाम करें।)",
     "severe": False},
    {"keywords": ["gout","uric acid","uric acid high","toe pain","गाउट"],
     "condition": "Gout (गाउट/वातरक्त)",
     "cause": "High uric acid deposits in joints. (जोड़ों में यूरिक एसिड जमा होना)",
     "remedy": "Avoid red meat and alcohol. Drink water, take prescribed medication. (लाल मांस और शराब से बचें।)",
     "severe": False},
    {"keywords": ["depression","sadness","tanav","udaasi","mental health","अवसाद"],
     "condition": "Depression (अवसाद/मानसिक तनाव)",
     "cause": "Chemical imbalance, stress, trauma or grief. (मानसिक तनाव या आघात)",
     "remedy": "Talk to a trusted person, exercise daily, consider counseling. Do not isolate. (किसी विश्वसनीय से बात करें और काउंसलर से मिलें।)",
     "severe": True},
    {"keywords": ["anxiety","ghabrahat","panic","nervous","घबराहट"],
     "condition": "Anxiety / Panic (घबराहट/चिंता)",
     "cause": "Excessive worry, stress or hormonal imbalance. (अत्यधिक चिंता और तनाव)",
     "remedy": "Deep breathing exercises, meditation. Avoid caffeine. Seek therapy if persistent. (गहरी सांस लें और ध्यान करें।)",
     "severe": False},
    {"keywords": ["insomnia","neend na aana","sleep problem","nidra","अनिद्रा"],
     "condition": "Insomnia (अनिद्रा/नींद न आना)",
     "cause": "Stress, screen time or irregular sleep schedule. (तनाव या अनियमित सोने का समय)",
     "remedy": "Fixed sleep schedule, reduce screens, warm milk before bed. (सोने का समय निश्चित करें और स्क्रीन कम देखें।)",
     "severe": False},
    {"keywords": ["sinusitis","sinus","naak band","blocked nose","साइनस"],
     "condition": "Sinusitis (साइनस इन्फेक्शन)",
     "cause": "Infection or allergy causing sinus inflammation. (एलर्जी या इन्फेक्शन से साइनस में सूजन)",
     "remedy": "Steam inhalation twice daily, saline nasal rinse, stay hydrated. (दिन में दो बार भाप लें।)",
     "severe": False},
    {"keywords": ["tonsils","tonsilitis","gale mein dard","throat infection","टॉन्सिल"],
     "condition": "Tonsillitis (टॉन्सिल का इन्फेक्शन)",
     "cause": "Bacterial or viral throat infection. (गले का बैक्टीरिया या वायरल इन्फेक्शन)",
     "remedy": "Gargle with warm salt water, honey-ginger tea. See doctor if fever develops. (गर्म पानी से गरारे करें।)",
     "severe": False},
    {"keywords": ["acne","pimple","muhase","skin breakout","मुँहासे"],
     "condition": "Acne / Pimples (मुँहासे)",
     "cause": "Excess sebum, bacteria or hormonal changes. (हार्मोनल बदलाव या बैक्टीरिया)",
     "remedy": "Wash face twice daily, apply neem paste or salicylic acid gel. Avoid squeezing. (चेहरा साफ रखें और नीम लगाएं।)",
     "severe": False},
    {"keywords": ["sunburn","dhoop se jalna","skin burn","UV damage","धूप की जलन"],
     "condition": "Sunburn (धूप की जलन)",
     "cause": "Prolonged UV radiation exposure. (अत्यधिक धूप में रहना)",
     "remedy": "Apply aloe vera gel, cool water compress, drink plenty of fluids. (एलोवेरा जेल लगाएं और पानी पिएं।)",
     "severe": False},
    {"keywords": ["heat stroke","loo","garmi","heat exhaustion","loo lagna","लू लगना"],
     "condition": "Heat Stroke / Loo (लू/गर्मी का दौरा)",
     "cause": "Prolonged exposure to extreme heat. (अत्यधिक गर्मी में रहना)",
     "remedy": "Move to shade, apply cold wet cloth, drink ORS. Seek emergency help if unconscious. (ठंडी जगह ले जाएं और ORS पिलाएं।)",
     "severe": True},
    {"keywords": ["hypothermia","thand","cold exposure","shivering","ठंड लगना"],
     "condition": "Hypothermia (अत्यधिक ठंड का असर)",
     "cause": "Prolonged cold weather exposure. (अत्यधिक ठंड में रहना)",
     "remedy": "Wrap in warm blankets, give warm liquids, move indoors. Call emergency if severe. (गर्म कंबल ओढ़ें और गर्म पेय दें।)",
     "severe": True},
    {"keywords": ["fracture","haddi tootna","broken bone","sprain","bone injury","हड्डी टूटना"],
     "condition": "Fracture (हड्डी टूटना)",
     "cause": "Trauma, fall or accident. (चोट, गिरना या दुर्घटना)",
     "remedy": "Immobilize the limb, apply ice pack, rush to hospital immediately. (हड्डी हिलाएँ नहीं और तुरंत अस्पताल जाएं।)",
     "severe": True},
    {"keywords": ["burn","jalna","fire injury","scald","जलना"],
     "condition": "Burn Injury (जलने की चोट)",
     "cause": "Fire, hot water or chemicals. (आग, गर्म पानी या रसायन)",
     "remedy": "Cool with running water for 10 min. Do not apply toothpaste or oil. See doctor. (ठंडे पानी से 10 मिनट धोएं। तेल मत लगाएं।)",
     "severe": True},
    {"keywords": ["nose bleed","naak se khoon","epistaxis","नाक से खून"],
     "condition": "Nosebleed (नाक से खून आना)",
     "cause": "Dry air, nose picking or high blood pressure. (सूखी हवा या नाक में चोट)",
     "remedy": "Sit upright, pinch nose for 10 minutes, lean slightly forward. (सीधे बैठें और 10 मिनट नाक दबाएं।)",
     "severe": False},
    {"keywords": ["leg cramp","pair mein ainth","muscle cramp","cramps","पैर में ऐंठन"],
     "condition": "Muscle Cramps (मांसपेशियों में ऐंठन)",
     "cause": "Electrolyte imbalance, dehydration or over-exertion. (इलेक्ट्रोलाइट की कमी या थकान)",
     "remedy": "Stretch the muscle, massage gently, drink banana shake or ORS. (मांसपेशी खींचें और केला खाएं।)",
     "severe": False},
    {"keywords": ["hiccup","hichki","hickup","हिचकी"],
     "condition": "Hiccups (हिचकी)",
     "cause": "Eating too fast, spicy food or sudden temperature change. (तेज खाना या मसालेदार खाना)",
     "remedy": "Hold breath for 10 seconds, drink cold water slowly, breathe into a paper bag. (10 सेकंड साँस रोकें और ठंडा पानी पिएं।)",
     "severe": False},
    {"keywords": ["vertigo","balance problem","chakkar aana","spinning","vestibular","चक्कर आना"],
     "condition": "Vertigo (सिर चकराना)",
     "cause": "Inner ear issue, low BP or dehydration. (भीतरी कान की समस्या या कम बीपी)",
     "remedy": "Lie still, avoid sudden movements. Drink water. See doctor if recurring. (लेट जाएं और पानी पिएं।)",
     "severe": False},
    {"keywords": ["epilepsy","seizure","fits","mirchhii","dauraa","मिर्गी"],
     "condition": "Epilepsy / Seizure (मिर्गी/दौरा)",
     "cause": "Abnormal electrical activity in brain. (मस्तिष्क में असामान्य विद्युत गतिविधि)",
     "remedy": "Keep patient safe, do not hold down, turn to side. Call emergency immediately. (मरीज को सुरक्षित रखें और एम्बुलेंस बुलाएं।)",
     "severe": True},
    {"keywords": ["chest pain","seene mein dard","heart pain","angina","सीने में दर्द"],
     "condition": "Chest Pain (सीने में दर्द)",
     "cause": "Could be heart-related, acidity or muscle strain. (दिल, गैस या मांसपेशियों की समस्या)",
     "remedy": "EMERGENCY: Call ambulance immediately. Do not ignore. Chew aspirin if available. (तुरंत एम्बुलेंस बुलाएं।)",
     "severe": True},
    {"keywords": ["stroke","paralysis","laqwa","face drooping","speech slur","पक्षाघात"],
     "condition": "Stroke (पक्षाघात/लकवा)",
     "cause": "Blood clot or bleeding in brain. (मस्तिष्क में रक्त का थक्का या रक्तस्राव)",
     "remedy": "EMERGENCY: Call ambulance immediately. Note the time of symptoms. Do not give food/water. (तुरंत 108 बुलाएं।)",
     "severe": True},
    {"keywords": ["food allergy","khane ki allergy","nuts allergy","shellfish allergy","खाने की एलर्जी"],
     "condition": "Food Allergy (खाने से एलर्जी)",
     "cause": "Immune overreaction to specific foods like nuts, dairy or shellfish. (कुछ खाद्य पदार्थों से इम्यून प्रतिक्रिया)",
     "remedy": "Avoid trigger food, take antihistamine. Carry EpiPen if prescribed. Seek emergency for anaphylaxis. (एलर्जी वाली चीज़ न खाएं।)",
     "severe": True},
    {"keywords": ["dehydration","pani ki kami","dry mouth","dark urine","निर्जलीकरण"],
     "condition": "Dehydration (निर्जलीकरण)",
     "cause": "Insufficient fluid intake or excess sweating. (पानी कम पीना या पसीना अधिक आना)",
     "remedy": "Drink water, ORS, coconut water or lemon-salt water regularly. (ORS और नारियल पानी पिएं।)",
     "severe": False},
    {"keywords": ["hepatitis","liver inflammation","hep A","hep B","यकृत शोथ"],
     "condition": "Hepatitis (हेपेटाइटिस/यकृत सूजन)",
     "cause": "Viral infection of liver (A, B or C type). (लिवर का वायरल इन्फेक्शन)",
     "remedy": "Rest, hydration, avoid alcohol. See doctor urgently for antiviral treatment. (डॉक्टर से तुरंत मिलें और शराब से बचें।)",
     "severe": True},
    {"keywords": ["pneumonia","lung infection","nikumonia","chest cold","निमोनिया"],
     "condition": "Pneumonia (निमोनिया/फेफड़ों का इन्फेक्शन)",
     "cause": "Bacterial or viral lung infection. (फेफड़ों का बैक्टीरिया/वायरल इन्फेक्शन)",
     "remedy": "See doctor immediately. Take antibiotics as prescribed. Rest and stay hydrated. (तुरंत डॉक्टर के पास जाएं।)",
     "severe": True},
    {"keywords": ["appendix","appendicitis","right side pain","appendix pain","अपेंडिक्स"],
     "condition": "Appendicitis (अपेंडिक्स की सूजन)",
     "cause": "Inflammation of appendix. (अपेंडिक्स में सूजन)",
     "remedy": "EMERGENCY: Go to hospital immediately. Do not eat, drink or apply heat. (तुरंत अस्पताल जाएं।)",
     "severe": True},
    {"keywords": ["hernia","ghutna","bulge","intestine","हर्निया"],
     "condition": "Hernia (हर्निया)",
     "cause": "Weakness in abdominal wall allowing organ protrusion. (पेट की दीवार की कमज़ोरी)",
     "remedy": "Avoid heavy lifting. Surgery is often required. Consult a surgeon. (भारी वजन न उठाएं और सर्जन से मिलें।)",
     "severe": True},
    {"keywords": ["obesity","mota","overweight","body weight","मोटापा"],
     "condition": "Obesity (मोटापा)",
     "cause": "Overeating, sedentary lifestyle or hormonal issues. (अधिक खाना और कम व्यायाम)",
     "remedy": "Balanced diet, daily 45-min walk, reduce sugar and fried foods. (संतुलित खाना खाएं और रोज़ चलें।)",
     "severe": False},
    {"keywords": ["vitamin D deficiency","vitamin D kami","bone weakness","sun exposure","विटामिन डी की कमी"],
     "condition": "Vitamin D Deficiency (विटामिन डी की कमी)",
     "cause": "Lack of sunlight exposure or poor diet. (धूप की कमी या पोषण की कमी)",
     "remedy": "10-15 min daily sunlight. Eat eggs, milk, fish. Take supplements if needed. (रोज़ 15 मिनट धूप लें।)",
     "severe": False},
    {"keywords": ["COVID","coronavirus","covid-19","corona","कोविड"],
     "condition": "COVID-19 (कोविड-19)",
     "cause": "SARS-CoV-2 virus spread through air droplets. (हवा के ज़रिए फैलने वाला कोरोना वायरस)",
     "remedy": "Isolate immediately, monitor oxygen levels, drink warm fluids. See doctor if oxygen drops below 95. (अलग हो जाएं और डॉक्टर से संपर्क करें।)",
     "severe": True},
]


# ─────────────────────────────────────────────
#  HELPER: convert ObjectId → str for templates
# ─────────────────────────────────────────────
def oid(doc_id):
    """Return string representation of an ObjectId."""
    return str(doc_id)


# --- 5. ROUTES ---

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        doc = users_col.find_one({"username": username, "password": password})
        if doc:
            user = User(doc)
            login_user(user)
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            if doc.get('role') == 'doctor':
                return redirect(url_for('doctor_panel', id=oid(doc['_id'])))
            return redirect(url_for('home'))
        flash('Login failed. Please check your credentials.')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    reason = request.args.get('reason')
    msg = "First register then ask" if reason == 'ask' else ""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name     = request.form.get('name')
        age      = request.form.get('age')
        if users_col.find_one({"username": username}):
            return render_template('register.html', alert_msg="Username already exists!")
        result = users_col.insert_one({
            "username": username, "password": password,
            "name": name, "age": age, "role": "patient"
        })
        user = User(users_col.find_one({"_id": result.inserted_id}))
        login_user(user)
        return redirect(url_for('home'))
    return render_template('register.html', alert_msg=msg)


@app.route('/register_doctor', methods=['GET', 'POST'])
def register_doctor():
    if request.method == 'POST':
        username        = request.form.get('username')
        password        = request.form.get('password')
        name            = request.form.get('name')
        age             = request.form.get('age')
        email           = request.form.get('email')
        phone           = request.form.get('phone')
        specialization  = request.form.get('specialization')
        hospital        = request.form.get('hospital')
        license_number  = request.form.get('license_number')

        if users_col.find_one({"username": username}):
            return render_template('register_doctor.html', alert_msg="Username already exists!")
        if users_col.find_one({"email": email}):
            return render_template('register_doctor.html', alert_msg="Email already registered!")

        result = users_col.insert_one({
            "username": username, "password": password,
            "name": name, "age": age, "email": email,
            "phone": phone, "specialization": specialization,
            "hospital": hospital, "license_number": license_number,
            "role": "doctor"
        })
        # Also insert into legacy doctors collection
       # doctors_col.insert_one({
          #  "name": name, "specialization": specialization,
          #  "hospital": hospital, "email": email
       # })
        user = User(users_col.find_one({"_id": result.inserted_id}))
        login_user(user)
        return redirect(url_for('doctor_panel', id=oid(result.inserted_id)))
    return render_template('register_doctor.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    doctors = list(users_col.find({"role": "doctor"}))
    # Stringify _id for template use
    for d in doctors:
        d['id'] = oid(d['_id'])

    my_appointments = list(appointments_col.find({"user_id": current_user.id}))
    for a in my_appointments:
        a['id'] = oid(a['_id'])
        # Attach doctor info
        doc_doc = users_col.find_one({"_id": ObjectId(a['doctor_id'])}) if ObjectId.is_valid(a['doctor_id']) else None
        a['doctor'] = User(doc_doc) if doc_doc else None

    history = list(health_logs_col.find({"user_id": current_user.id}).sort("_id", -1))
    for h in history:
        h['id'] = oid(h['_id'])

    weight_logs = list(weight_logs_col.find({"user_id": current_user.id}).sort("_id", 1))
    dates   = [log.get('date', '') for log in weight_logs]
    weights = [log.get('weight', 0) for log in weight_logs]

    return render_template('dashboard.html',
                           user=current_user,
                           doctors=doctors,
                           appointments=my_appointments,
                           history=history,
                           graph_dates=dates,
                           graph_weights=weights)


@app.route('/book_appointment', methods=['POST'])
@login_required
def book_appointment():
    doctor_id = request.form.get('doctor_id')
    date      = request.form.get('date')
    reason    = request.form.get('reason')

    if doctor_id and date and reason:
        # doctor_id here comes from the legacy doctors collection
        doctor = users_col.find_one({"_id": ObjectId(doctor_id), "role": "doctor"}) if ObjectId.is_valid(doctor_id) else None
        result = appointments_col.insert_one({
            "user_id":   current_user.id,
            "doctor_id": doctor_id,
            "date":      date,
            "reason":    reason,
            "status":    "Pending"
        })
        if doctor:
            send_doctor_alert(
                doctor['name'], current_user.username, date,
                doctor['email'], oid(result.inserted_id), doctor_id
            )
            flash('Appointment Request Sent!', 'success')
    else:
        flash('Please fill all fields (Date & Time).', 'error')
    return redirect(url_for('dashboard'))


@app.route('/save_weight', methods=['POST'])
@login_required
def save_weight():
    data   = request.get_json()
    weight = data.get('weight')
    if weight:
        weight_logs_col.insert_one({
            "user_id": current_user.id,
            "weight":  weight,
            "date":    datetime.now().strftime("%d-%b")
        })
        return jsonify({"message": "Saved"})
    return jsonify({"message": "Error"}), 400


@app.route('/get_advice', methods=['POST'])
def get_advice():
    try:
        data     = request.get_json()
        symptoms = data.get('symptoms', '').lower()

        selected_lang = data.get('language', 'English')

        found_conditions = []
        advice_list      = []
        see_doctor       = False

        for item in MEDICAL_DATA:
            for key in item["keywords"]:
                if key in symptoms:
                    found_conditions.append({
                        "name":     item["condition"],
                        "cause":    item["cause"],
                        "solution": item["remedy"]
                    })
                    advice_list.append(item["remedy"])
                    if item["severe"]:
                        see_doctor = True
                    break

        if not found_conditions:
            found_conditions.append({
                "name":     "Unidentified (समझ नहीं आया)",
                "cause":    "Not in database. (डेटाबेस में नहीं है)",
                "solution": "Please consult a doctor. (कृपया डॉक्टर से मिलें।)"
            })
            advice_list.append("I didn't understand. Try 'Fever' or 'Bukhar'.")

            if selected_lang == 'Hindi':
                translator = GoogleTranslator(source='en', target='hi')
                
                # Conditions ko Hindi mein badalna
                for cond in found_conditions:
                    cond["name"] = translator.translate(cond["name"])
                    cond["cause"] = translator.translate(cond["cause"])
                    cond["solution"] = translator.translate(cond["solution"])
                
                # Advice list ko Hindi mein badalna
                advice_list = [translator.translate(adv) for adv in advice_list]

        general_advice = " | ".join(advice_list) if advice_list else "Please consult a doctor."

        response = {
            "conditions": found_conditions,
            "advice":     general_advice,
            "see_doctor": see_doctor
        }

        if current_user.is_authenticated:
            condition_names = ", ".join([c['name'] for c in found_conditions])
            health_logs_col.insert_one({
                "user_id":   current_user.id,
                "symptoms":  symptoms,
                "advice":    f"Found: {condition_names}. Advice: {general_advice}",
                "date_time": datetime.now().strftime("%d-%m-%Y %I:%M %p")
            })

        return jsonify(response)
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"advice": "System Error.", "conditions": []})


@app.route('/doctor_panel/<string:id>')
@login_required
def doctor_panel(id):
    if current_user.id != id or current_user.role != 'doctor':
        flash('Unauthorized access!')
        return redirect(url_for('login'))

    appointments = list(appointments_col.find({"doctor_id": id}).sort("status", -1))
    for a in appointments:
        a['id'] = oid(a['_id'])
        # Attach patient info
        patient_doc = users_col.find_one({"_id": ObjectId(a['user_id'])}) if ObjectId.is_valid(a['user_id']) else None
        a['user'] = User(patient_doc) if patient_doc else None

    patient_histories = {}
    for appt in appointments:
        patient_id = appt.get('user_id')
        if patient_id and patient_id not in patient_histories:
            history = list(health_logs_col.find({"user_id": patient_id}).sort("_id", -1).limit(5))
            for h in history:
                h['id'] = oid(h['_id'])
            patient_histories[patient_id] = history

    return render_template('doctor_panel.html',
                           doctor=current_user,
                           appointments=appointments,
                           patient_histories=patient_histories)


@app.route('/update_appt_status/<string:id>/<string:status>')
@login_required
def update_appt_status(id, status):
    appt = appointments_col.find_one({"_id": ObjectId(id)})
    if not appt or current_user.id != appt['doctor_id']:
        flash('Unauthorized!')
        return redirect(url_for('login'))
    appointments_col.update_one({"_id": ObjectId(id)}, {"$set": {"status": status}})
    return redirect(url_for('doctor_panel', id=appt['doctor_id']))


@app.route('/delete_log/<string:id>')
@login_required
def delete_log(id):
    log = health_logs_col.find_one({"_id": ObjectId(id)})
    if log and log.get('user_id') == current_user.id:
        health_logs_col.delete_one({"_id": ObjectId(id)})
    return redirect(url_for('dashboard'))


@app.route('/clear_history')
@login_required
def clear_history():
    health_logs_col.delete_many({"user_id": current_user.id})
    return redirect(url_for('dashboard'))


@app.route('/setup')
def setup():
    """Seed the database with 6 default doctors."""
    MY_EMAIL = "vt665962@gmail.com"
    if doctors_col.count_documents({}) == 0:
        doctors = [
            {"name": "Dr. Amit Sharma",    "specialization": "Cardiologist (Heart)",  "hospital": "City Heart Center",    "email": MY_EMAIL},
            {"name": "Dr. Sneha Verma",    "specialization": "Dermatologist (Skin)",  "hospital": "Skin Care Clinic",     "email": MY_EMAIL},
            {"name": "Dr. Rahul Singh",    "specialization": "General Physician",     "hospital": "City Hospital",        "email": MY_EMAIL},
            {"name": "Dr. Priya Das",      "specialization": "Pediatrician (Child)",  "hospital": "Star Kids Hospital",   "email": MY_EMAIL},
            {"name": "Dr. Vikram Malhotra","specialization": "Orthopedic (Bone)",     "hospital": "Ortho Care Unit",      "email": MY_EMAIL},
            {"name": "Dr. Anjali Mehta",   "specialization": "Dentist (Teeth)",       "hospital": "Smile Dental Clinic",  "email": MY_EMAIL},
        ]
        doctors_col.insert_many(doctors)
        return "✅ MongoDB seeded with 6 Doctors! Go to <a href='/login'>Login</a>"
    return "Doctors already exist. Go to <a href='/login'>Login</a>"


if __name__ == '__main__':
    app.run(debug=True, port=5000)