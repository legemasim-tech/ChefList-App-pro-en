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

amazon_tag_us = "cheflist21-20" 
paypal_email = "legemasim@gmail.com"
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
    base_value = 17 
    if os.path.exists(file_path):
        try:
            with open(file_path, "r") as f: 
                return int(f.read()) + base_value
        except: return base_value
    return base_value

# --- 2. HELPER FUNCTIONS ---
def get_full_video_data(video_url):
    try:
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
        subs = info.get('subtitles') or info.get('automatic_captions')
        transcript = ""
        
        if subs:
            target_url = None
            for lang in ['en', 'de', 'en-orig', 'de-orig']:
                if lang in subs:
                    for f in subs[lang]:
                        if f.get('ext') == 'json3':
                            target_url = f.get('url')
                            break
                    if target_url: break
            if target_url:
                res = requests.get(target_url)
                if res.status_code == 200:
                    data = res.json()
                    transcript = " ".join([seg.get('utf8', '').strip() for event in data.get('events', []) if 'segs' in event for seg in event['segs'] if seg.get('utf8', '')])
        
        return video_title, transcript, description, channel_name
    except Exception as e:
        return "Recipe", None, None, "Unknown Chef"

def generate_smart_recipe(video_title, channel_name, transcript, description, tag, portions, unit_system):
    combined_input = f"ORIGINAL TITLE: {video_title}\nSOURCE CHANNEL: {channel_name}\n\nTRANSCRIPT:\n{transcript}\n\nDESCRIPTION:\n{description}"
    unit_instruction = "US UNITS (cups, oz, lbs, tsp, tbsp)." if unit_system == "US Units (cups/oz)" else "METRIC (g, ml, kg, l)."
    
    system_prompt = f"""Professional Chef Mode. Convert recipe to {portions} servings. Units: {unit_instruction} Language: English. Format: TITLE: [Name] by [Author], Key Data, Ingredients Table (with Amazon links: tag={tag}), Step-by-step Instructions."""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": combined_input[:16000]}]
        )
        return response.choices[0].message.content
    except: return None

# --- 3. PDF GENERATOR ---
def clean_for_pdf(text):
    replacements = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue', 'ß': 'ss'}
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    text = text.replace('“', '"').replace('”', '"').replace('’', "'").replace('–', '-')
    text = re.sub(r'[^\x00-\x7F]+', '', text)
    return text

def create_pdf(text_content, recipe_title):
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", style="B", size=14)
        pdf.cell(190, 15, txt=f"Recipe: {clean_for_pdf(recipe_title[:40])}", ln=True, align='C', fill=False)
        pdf.ln(5)
        pdf.set_font("Arial", size=10)
        pdf.multi_cell(0, 7, txt=clean_for_pdf(text_content))
        return pdf.output()
    except: return None

# --- 4. STREAMLIT INTERFACE ---
st.set_page_config(page_title="ChefList Pro EN", page_icon="🍲")

if "counter_en" not in st.session_state: st.session_state.counter_en = 0
if "recipe_result_en" not in st.session_state: st.session_state.recipe_result_en = None

with st.sidebar:
    st.title("🍳 ChefList Pro")
    st.info(f"Recipes created: {st.session_state.counter_en}")
    st.markdown(f'''<a href="{pay_link_90c}" target="_blank"><button style="width: 100%; background-color: #0070ba; color: white; border: none; padding: 10px; border-radius: 5px; cursor: pointer; font-weight: bold;">⚡ Support ChefList Pro ($0.90)</button></a>''', unsafe_allow_html=True)
    st.markdown('<p style="text-align: center; font-size: 0.8em; margin-top: 10px;"><a href="https://de.cheflist.pro" target="_blank">Switch to German Version</a></p>', unsafe_allow_html=True)
    
    # Check for feedback
    new_indicator = " 🔴" if os.path.exists("user_feedback.txt") and os.path.getsize("user_feedback.txt") > 0 else ""
    
    st.markdown("---")
    with st.expander(f"ℹ️ About & Legal{new_indicator}"):
        st.caption("**Operator:** Markus Simmel\n**Contact:** legemasim@gmail.com")
        st.write(f"📊 Total recipes: **{get_total_count()}**")
        st.divider()
        if st.checkbox("🔑 Admin Access"):
            admin_pw = st.text_input("Password", type="password", key="admin_pw_input")
            if admin_pw == "Gemini_Cheflist_pw":
                if os.path.exists("user_feedback.txt"):
                    with open("user_feedback.txt", "r") as f: content = f.read()
                    st.text_area("Messages:", value=content, height=200)
                    if st.button("Clear Log"):
                        with open("user_feedback.txt", "w") as f: f.write("")
                        st.rerun()
            elif admin_pw: st.error("Wrong password")

st.title("🍲 ChefList Pro")
video_url = st.text_input("YouTube URL:", placeholder="https://...")
col1, col2 = st.columns(2)
portions = col1.slider("Servings:", 1, 10, 4)
unit_system = col2.radio("Units:", ["US Units (cups/oz)", "Metric (g/ml)"])

if st.button("Create Recipe ✨", use_container_width=True):
    if video_url:
        with st.status("Processing...") as status:
            title_orig, transcript, description, chef = get_full_video_data(video_url)
            result = generate_smart_recipe(title_orig, chef, transcript, description, amazon_tag_us, portions, unit_system)
            if result:
                st.session_state.recipe_result_en = result
                st.session_state.recipe_title_en = result.split('\n')[0].replace('TITLE:', '').strip()
                st.session_state.counter_en += 1
                update_global_counter()
                status.update(label="Done!", state="complete")

if st.session_state.get("recipe_result_en"):
    st.divider()
    st.subheader(st.session_state.recipe_title_en)
    st.markdown(st.session_state.recipe_result_en)
    pdf_bytes = create_pdf(st.session_state.recipe_result_en, st.session_state.recipe_title_en)
    if pdf_bytes:
        st.download_button("📄 Download PDF", data=bytes(pdf_bytes), file_name="Recipe.pdf", mime="application/pdf")

# --- FEEDBACK ---
st.divider()
with st.form("feedback_form"):
    fb_text = st.text_area("Feedback & Ideas:")
    fb_mail = st.text_input("Email (optional):")
    if st.form_submit_button("Send"):
        if fb_text:
            with open("user_feedback.txt", "a") as f: f.write(f"From: {fb_mail}\n{fb_text}\n---\n")
            st.success("Thanks!")
