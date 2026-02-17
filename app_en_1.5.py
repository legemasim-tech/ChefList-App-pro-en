import streamlit as st
import openai
import requests
import re
import yt_dlp
from fpdf import FPDF
import os

# --- 1. CONFIGURATION & API ---
try:
    api_key = st.secrets["OPENAI_API_KEY"]
except:
    api_key = None

# Changed to .com and a generic or new tag for the US market
amazon_tag_us = "cheflist21-20" 
paypal_email = "legemasim@gmail.com"

# Update payment link for international audience (USD/EUR)
pay_link_90c = f"https://www.paypal.com/cgi-bin/webscr?cmd=_xclick&business={paypal_email}&item_name=ChefList_Pro_Support&amount=0.90&currency_code=USD"

if not api_key:
    st.error("Please add your OpenAI API Key to Streamlit Secrets!")
    st.stop()

client = openai.OpenAI(api_key=api_key)

# --- GLOBAL COUNTER ---
def update_global_counter():
    file_path = "total_recipes_en.txt"
    try:
        if not os.path.exists(file_path):
            with open(file_path, "w") as f: f.write("0")
        with open(file_path, "r") as f: count = int(f.read())
        count += 1
        with open(file_path, "w") as f: f.write(str(count))
        return count
    except: return 0

def get_total_count():
    file_path = "total_recipes_en.txt"
    base_value = 17 # Starting value for social proof
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f: 
                return int(f.read()) + base_value
        except: return base_value
    return base_value

# --- 2. HELPER FUNCTIONS ---
def get_full_video_data(video_url):
    try:
        # Wir suchen gezielt nach gängigen Sprachen
        ydl_opts = {
            'quiet': True, 
            'skip_download': True, 
            'writesubtitles': True, 
            'writeautomaticsub': True, 
            'subtitleslangs': ['en', 'de', 'es', 'fr', 'it', 'pt'] 
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
        
        video_title = info.get('title', 'Recipe')
        channel_name = info.get('uploader', 'Unknown Chef')
        description = info.get('description', '') 
        
        # Suche in manuellen oder automatischen Untertiteln
        subs = info.get('subtitles') or info.get('automatic_captions')
        transcript = ""
        
        if subs:
            target_url = None
            # Priorität für Sprachen
            for lang in ['en', 'de', 'en-orig', 'de-orig', 'es', 'fr']:
                if lang in subs:
                    for f in subs[lang]:
                        if f.get('ext') == 'json3':
                            target_url = f.get('url')
                            break
                    if target_url: break
            
            # Fallback auf irgendwelche Untertitel
            if not target_url:
                for lang_code in subs.keys():
                    for f in subs[lang_code]:
                        if f.get('ext') == 'json3':
                            target_url = f.get('url')
                            break
                    if target_url: break

            if target_url:
                res = requests.get(target_url)
                if res.status_code == 200:
                    data = res.json()
                    transcript = " ".join([
                        seg.get('utf8', '').strip() 
                        for event in data.get('events', []) 
                        if 'segs' in event 
                        for seg in event['segs'] 
                        if seg.get('utf8', '')
                    ])
        
        # WICHTIG: Diese Zeile muss genau unter dem 'if subs:' Block stehen
        return video_title, transcript, description, channel_name

    except Exception as e:
        print(f"Debug Error: {e}")
        # WICHTIG: Hier geben wir 4 Werte zurück für die Sicherheit
        return "Recipe", None, None, "Unknown Chef"

def generate_smart_recipe(video_title, channel_name, transcript, description, tag, portions, unit_system):
    # Wir geben der KI jetzt auch den originalen Titel
    combined_input = f"ORIGINAL TITLE: {video_title}\nSOURCE CHANNEL: {channel_name}\n\nTRANSCRIPT:\n{transcript}\n\nDESCRIPTION:\n{description}"
    
    unit_instruction = "US UNITS (cups, oz, lbs, tsp, tbsp). If the source is metric, YOU MUST CONVERT them to US units!" if unit_system == "US Units (cups/oz)" else "METRIC (g, ml, kg, l)."
    
    system_prompt = f"""
    You are a professional chef and a high-precision mathematician.
    
    MAIN TASK: 
    1. TRANSLATE the recipe title into an appealing English title.
    2. Identify the original serving size from the video.
    3. Recalculate and CONVERT all quantities EXACTLY for {portions} person(s). 
    4. IMPORTANT: Use {unit_instruction}
    5. Write the entire recipe in ENGLISH.
    
    STRUCTURE:
    - TITLE: Write the title in this exact format: "[English Recipe Name] by [Author/Channel Name]"
       Example: "Easiest Beef Wellington by Joshua Weissman"
    - Key Data (Time, difficulty, servings: {portions})
    - Ingredients Table (Amount | Ingredient | Shop)
      -> Link: https://www.amazon.com/s?k=[INGREDIENTNAME]&tag={tag}
      -> Link-Text: '🛒 buy on Amazon*'
    - Instructions (Step-by-step)
    
    Start your response directly with the TITLE."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": combined_input[:16000]}]
        )
        return response.choices[0].message.content
    except: return None

# --- 3. PDF GENERATOR ---
def clean_for_pdf(text):
    # Deine bewährte Reinigungs-Logik
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss', '€': 'Euro'}
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    
    # WICHTIG: Die KI nutzt im Englischen oft "smarte" Anführungszeichen (curly quotes)
    # Diese müssen wir für das PDF-Modul glätten:
    text = text.replace('“', '"').replace('”', '"').replace('’', "'").replace('–', '-')
    
    # Entfernt alles Nicht-ASCII (was das PDF-Modul zum Absturz bringt)
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return text

def create_pdf(text_content, recipe_title):
    try:
        pdf = FPDF()
        pdf.set_left_margin(10)
        pdf.set_right_margin(10)
        pdf.add_page()
        pdf.set_fill_color(230, 230, 230) 
        pdf.set_font("Arial", style="B", size=14)
        
        # Header - Wir schreiben "Recipe:" statt "Rezept:"
        display_title = clean_for_pdf(recipe_title if len(recipe_title) <= 40 else recipe_title[:37] + "...")
        pdf.cell(190, 15, txt=f"Recipe: {display_title}", ln=True, align='C', fill=True)
        pdf.ln(5)
        
        lines = text_content.split('\n')
        is_instruction = False
        for line in lines:
            line = line.strip()
            if not line or '---' in line: continue
            line = clean_for_pdf(line)
            
            # WICHTIG: Wir prüfen auf englische Schlüsselwörter
            if any(word in line for word in ['Instructions', 'Preparation', 'Directions']):
                is_instruction = True
                pdf.ln(5)
                pdf.set_font("Arial", style="B", size=12)
                pdf.cell(0, 10, txt="Instructions:", ln=True)
                continue
                
            # Englische Header erkennen
            headers = ['Time:', 'Difficulty:', 'Temperature:', 'Servings:', 'Units:']
            if any(line.startswith(h) for h in headers):
                pdf.set_font("Arial", style="B", size=11)
                pdf.cell(0, 8, txt=line, ln=True)
                continue
                
            pdf.set_x(10)
            if '|' in line and not is_instruction:
                parts = [p.strip() for p in line.split('|') if p.strip()]
                if len(parts) >= 2:
                    # Spaltenköpfe auf Englisch prüfen
                    if "Amount" in parts[0] or "Ingredient" in parts[1]:
                        pdf.set_font("Arial", style="B", size=10)
                        content = "AMOUNT - INGREDIENT"
                    else:
                        pdf.set_font("Arial", style="B", size=11)
                        content = f"[  ] {parts[0].replace('*','')} {parts[1].replace('*','')}"
                    
                    # Breite auf 185 reduzieren, um den "Horizontal Space" Fehler zu vermeiden
                    pdf.cell(185, 8, txt=content, ln=True)
                    pdf.set_draw_color(220, 220, 220)
                    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            else:
                pdf.set_font("Arial", size=10)
                # multi_cell ebenfalls leicht schmaler (185 statt 190)
                pdf.multi_cell(185, 7, txt=line.replace('*', ''), align='L')
                if is_instruction: pdf.ln(2)
                
        pdf.ln(10)
        pdf.set_font("Arial", style="I", size=10)
        pdf.cell(0, 10, txt="Enjoy your meal - Team ChefList Pro!", ln=True, align='C')
        
        # In fpdf2 liefert output() direkt Bytes
        return pdf.output()
    except Exception as e:
        # Das schreibt den Fehler in deine Streamlit Logs
        print(f"PDF Debug: {e}")
        return None
        
# --- 4. STREAMLIT INTERFACE ---
st.set_page_config(page_title="ChefList Pro EN", page_icon="🍲", layout="centered")

# Custom Logo CSS
st.markdown("<style>[data-testid='stSidebar'] img { background-color: white; padding: 10px; border-radius: 12px; border: 2px solid #e0e0e0; margin-bottom: 20px; }</style>", unsafe_allow_html=True)

if "counter_en" not in st.session_state: st.session_state.counter_en = 0
if "recipe_result_en" not in st.session_state: st.session_state.recipe_result_en = None

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.title("🍳 ChefList Pro")
    st.info(f"Recipes created: {st.session_state.counter_en}")
    
    # Der bestehende Support Button
    st.markdown(f'''<a href="{pay_link_90c}" target="_blank"><button style="width: 100%; background-color: #0070ba; color: white; border: none; padding: 10px; border-radius: 5px; cursor: pointer; font-weight: bold;">⚡ Support ChefList Pro ($0.90)</button></a>''', unsafe_allow_html=True)
    
    # NEU: Kleiner Hinweis-Link direkt darunter
    st.markdown('<p style="text-align: center; font-size: 0.8em; margin-top: 10px;"><a href="https://cheflist-app-de.streamlit.app/" target="_blank">Switch to German Version</a></p>', unsafe_allow_html=True)
 # --- PRÜFUNG AUF NEUES FEEDBACK ---
    new_feedback_indicator = ""
    if os.path.exists("user_feedback.txt"):
        if os.path.getsize("user_feedback.txt") > 0:
            # Ein roter Punkt als Emoji
            new_feedback_indicator = " 🔴"

    st.markdown("---")
    # Der Titel des Expanders ändert sich jetzt, wenn Feedback da ist
    with st.expander(f"ℹ️ About & Legal{new_feedback_indicator}"):
        st.caption("**Operator:** Markus Simmel\n\n**Contact:** legemasim@gmail.com")
        st.divider()
        st.write(f"📊 Total recipes generated: **{get_total_count()}**")
        st.divider()
        st.caption("✨ As an Amazon Associate, I earn from qualifying purchases.")
        st.divider()
        st.subheader("🛡️ Data Protection")
        st.caption("We do not store personal data. Processing is encrypted.")
        st.divider()
        st.caption("⚠️ **Note:** This app uses AI. AI can make mistakes – please verify cooking times and temperatures.")

# --- DER VERSTECKTE ADMIN-BEREICH GANZ UNTEN ---
        st.divider()
        if st.checkbox("🔑 Admin Access"):
            admin_pw = st.text_input("Password", type="password", key="admin_pw_input")
            if admin_pw == "Gemini_Cheflist_pw": # Ersetze dies durch dein Passwort!
                if os.path.exists("user_feedback.txt"):
                    with open("user_feedback.txt", "r") as f:
                        content = f.read()
                    if content:
                        st.text_area("User Messages:", value=content, height=300)
                        if st.button("Clear Feedback Log"):
                            with open("user_feedback.txt", "w") as f:
                                f.write("")
                            st.rerun()
                    else:
                        st.write("No messages yet.")
                else:
                    st.write("File not found.")
            elif admin_pw:
                st.error("Wrong password")

st.title("🍲 ChefList Pro")
st.subheader("Convert YouTube recipes into printable PDFs")

video_url = st.text_input("YouTube Video URL:", placeholder="https://www.youtube.com/watch?v=...")
col_opt1, col_opt2 = st.columns(2)
portions = col_opt1.slider("Servings:", 1, 10, 4)

# GEÄNDERT: US Units ist jetzt an erster Stelle (Standard)
unit_system = col_opt2.radio("Unit System:", ["US Units (cups/oz)", "Metric (g/ml)"], horizontal=True)

if st.button("Create Recipe ✨", use_container_width=True):
    if video_url:
        with st.status(f"Calculating recipe for {portions} servings...", expanded=True) as status:
            # FIX 1: channel_name hinzugefügt
            title_orig, transcript, description, channel_name = get_full_video_data(video_url)
            
            if transcript or description:
                # FIX 2: channel_name an Funktion übergeben
                result = generate_smart_recipe(title_orig, channel_name, transcript, description, amazon_tag_us, portions, unit_system)
                
                if result:
                    lines = result.split('\n')
                    new_title = lines[0].replace('TITLE:', '').replace('Title:', '').strip()
                    
                    st.session_state.recipe_result_en = result
                    st.session_state.recipe_title_en = new_title
                    st.session_state.counter_en += 1
                    update_global_counter()
                    status.update(label="Ready!", state="complete", expanded=False)
                else:
                    st.error("AI Generation failed.")
            else:
                st.error("No data found.")

if st.session_state.get("recipe_result_en"):
    st.divider()
    st.subheader(f"📖 {st.session_state.recipe_title_en}")
    st.markdown(st.session_state.recipe_result_en.replace("Check on Amazon", "Buy on Amazon"))
    
    st.divider()
    
    # 1. PDF generieren
    pdf_output = create_pdf(st.session_state.recipe_result_en, st.session_state.recipe_title_en)
    
    # 2. Sicherstellen, dass wir echte Bytes haben
    if pdf_output is not None:
        # Falls pdf_output bereits bytes sind (fpdf2), ist es gut.
        # Falls es ein String/andere Form ist, wandeln wir es um.
        try:
            pdf_bytes = bytes(pdf_output)
        except:
            pdf_bytes = pdf_output # fpdf2 gibt meist schon bytes aus
            
        st.download_button(
            label="📄 Download PDF Recipe", 
            data=pdf_bytes, 
            file_name="ChefList_Recipe.pdf", 
            mime="application/pdf", 
            use_container_width=True
        )
    else:
        st.error("The PDF could not be generated. Please check if the recipe text contains special characters.")

# --- FEEDBACK SECTION ---
st.divider()
st.subheader("Help us improve! 🍲")
with st.form("feedback_form"):
    feedback_text = st.text_area("What can we do better? (Errors, wishes, ideas)")
    user_email = st.text_input("Your email (optional, if you want a reply)")
    submit_feedback = st.form_submit_button("Send Feedback ✨")

    if submit_feedback:
        if feedback_text:
            # Hier speichern wir das Feedback in einer einfachen Textdatei
            feedback_entry = f"Email: {user_email}\nFeedback: {feedback_text}\n---\n"
            try:
                with open("user_feedback.txt", "a") as f:
                    f.write(feedback_entry)
                st.success("Thank you! Your feedback has been saved. We'll look into it! 🙌")
            except:
                st.error("Something went wrong. Please try again later.")
        else:
            st.warning("Please enter some text before sending.")
