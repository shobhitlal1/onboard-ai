"""Streamlit is an HTTP client; only FastAPI talks to the database."""

import os
from datetime import datetime

import httpx
import streamlit as st

from llm_service import SAMPLE_NOTES

st.set_page_config(page_title="OnboardAI · Client onboarding", page_icon="◈", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1180px; padding-top: 2.6rem; padding-bottom: 2rem;}
h1, h2, h3 {letter-spacing: -0.035em;}
[data-testid="stMetric"] {background: white; border: 1px solid #dfe6e9; border-radius: 12px; padding: 20px 24px;}
[data-testid="stMetricLabel"] {color: #60727b;}
[data-testid="stMetricValue"] {font-weight: 600;}
div.stButton > button {border-radius: 8px;}
.brand {font-size: 25px; font-weight: 750; letter-spacing: -1px; color: #162b36;}
.brand span {color: #176b5b;}
.eyebrow {font-size: 11px; letter-spacing: 2px; color: #637780; font-weight: 650; margin: 24px 0 8px;}
.intro {color: #62737d; font-size: 16px; margin-top: -8px; margin-bottom: 25px;}
</style>
""", unsafe_allow_html=True)

API_BASE = os.getenv("API_BASE_URL", "http://127.0.0.1:8000").rstrip("/")


def api_request(method: str, path: str, payload: dict | None = None):
    try:
        response = httpx.request(method, f"{API_BASE}{path}", json=payload, timeout=60)
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as error:
        detail = error.response.json().get("detail", "The request could not be completed.")
        st.error(detail if isinstance(detail, str) else "Please check the input and try again.")
    except httpx.RequestError:
        st.error("Cannot reach the API. Start it with: python -m uvicorn api:app --reload")
    st.stop()


def volume_label(value) -> str:
    return f"${value:,.0f}" if value is not None else "Not provided"


def status_label(status: str) -> str:
    return "Ready for review" if status == "READY_FOR_REVIEW" else "Incomplete"


def client_details(client: dict) -> None:
    st.subheader(client["company_name"])
    if client["status"] == "READY_FOR_REVIEW":
        st.success("READY_FOR_REVIEW · Document checklist complete")
    else:
        st.warning(f"INCOMPLETE · {len(client['missing_documents'])} documents to collect")
    cols = st.columns(4)
    for col, title, value in zip(cols, ["PRIMARY CONTACT", "ACCOUNT TYPE", "STATE", "MONTHLY VOLUME"],
                                 [client["contact_name"] or "Not provided", client["account_type"],
                                  client["state"] or "Not provided", volume_label(client["expected_monthly_volume"])]):
        col.caption(title)
        col.write(value)


health = api_request("GET", "/health")
clients = api_request("GET", "/clients")
brand, mode = st.columns([4, 1])
brand.markdown('<div class="brand">◈ Onboard<span>AI</span></div>', unsafe_allow_html=True)
mode.caption("●  MOCK MODE · OFFLINE" if health["llm_mode"] == "mock" else "●  OPENAI MODE")
st.caption("AI-assisted FinTech client onboarding")
page = st.radio("Workspace", ["Dashboard", "New client", "Client workspace"], horizontal=True, label_visibility="collapsed")
st.divider()

if page == "Dashboard":
    st.markdown('<div class="eyebrow">WORKSPACE OVERVIEW</div>', unsafe_allow_html=True)
    st.title("A clear path from intake to review.")
    st.markdown('<div class="intro">Track every client, collect the missing pieces, and keep the next step in view.</div>', unsafe_allow_html=True)
    total = len(clients)
    ready = sum(client["status"] == "READY_FOR_REVIEW" for client in clients)
    c1, c2, c3 = st.columns(3)
    c1.metric("Total clients", total)
    c2.metric("Incomplete", total - ready)
    c3.metric("Ready for review", ready)
    st.subheader("Client pipeline")
    st.caption("One document checklist. A visible history for every client.")
    if clients:
        st.dataframe([
            {"Client": client["company_name"], "Contact": client["contact_name"] or "Not provided",
             "Account": client["account_type"], "Monthly volume": volume_label(client["expected_monthly_volume"]),
             "Documents": f"{4 - len(client['missing_documents'])} / 4",
             "Status": status_label(client["status"])} for client in clients
        ], hide_index=True, width="stretch")
    else:
        st.info("Your workspace is ready. Open New client to process the pre-filled sample note.")
    with st.container(border=True):
        st.markdown("**From note to next step**")
        a, b, c = st.columns(3)
        a.write("**01 · Extract**")
        a.caption("Turn an onboarding note into structured client data.")
        b.write("**02 · Check**")
        b.caption("Python checks the four required document flags.")
        c.write("**03 · Review**")
        c.caption("Complete the checklist and record a simulated handoff.")

elif page == "New client":
    st.markdown('<div class="eyebrow">CLIENT INTAKE</div>', unsafe_allow_html=True)
    st.title("Start with a note.")
    st.markdown('<div class="intro">Capture client details and find exactly what still needs to be collected.</div>', unsafe_allow_html=True)
    if health["llm_mode"] == "mock":
        st.info("Offline demo: choose one of the three sample notes. Custom notes require OpenAI mode.")
    sample = st.selectbox("Sample note", list(SAMPLE_NOTES))
    with st.form("intake"):
        note = st.text_area("Paste onboarding note", value=SAMPLE_NOTES[sample], height=170, key=f"note_{sample}")
        submitted = st.form_submit_button("Process Client", type="primary")
    if submitted:
        with st.spinner("Extracting details and checking documents…"):
            result = api_request("POST", "/clients/from-note", {"note": note})
        st.session_state["processed_client"] = result
    result = st.session_state.get("processed_client")
    if result:
        st.divider()
        client_details(result)
        left, right = st.columns(2)
        left.markdown("**Received documents**")
        left.write(", ".join(d["document_type"] for d in result["documents"] if d["received"]) or "None yet")
        right.markdown("**Missing documents**")
        right.write(", ".join(result["missing_documents"]) or "None")
        with st.container(border=True):
            labels = {"mock": "AI summary · simulated in mock mode", "openai": "AI-assisted summary", "rules": "Checklist summary · fallback"}
            st.markdown(f"**{labels[result['summary_source']]}**")
            st.write(result["summary"])
        st.caption("Saved to SQLite. Open Client workspace to collect documents and view the activity log.")

else:
    st.markdown('<div class="eyebrow">DOCUMENTS & ACTIVITY</div>', unsafe_allow_html=True)
    st.title("Keep onboarding moving.")
    if not clients:
        st.info("Process a sample note in New client to begin.")
    else:
        by_id = {client["id"]: client for client in clients}
        client_id = st.selectbox("Select client", list(by_id), format_func=lambda value: f"{by_id[value]['company_name']} · #{value}")
        client = api_request("GET", f"/clients/{client_id}")
        client_details(client)
        st.divider()
        checklist, activity = st.columns([1, 1.2], gap="large")
        with checklist:
            st.subheader("Document checklist")
            received = 4 - len(client["missing_documents"])
            st.progress(received / 4, text=f"{received} of 4 documents received")
            for document in client["documents"]:
                with st.container(border=True):
                    st.write(document["document_type"])
                    if document["received"]:
                        st.caption("✓ Received")
                    elif st.button("Mark as received", key=f"doc_{document['id']}"):
                        api_request("POST", f"/clients/{client_id}/documents", {"document_type": document["document_type"]})
                        # Avoid showing an old summary on the intake page after an update.
                        st.session_state.pop("processed_client", None)
                        st.rerun()
            st.info(client["summary"])
        with activity:
            st.subheader("Workflow activity")
            st.caption("Recorded in order · all times UTC")
            events = api_request("GET", f"/clients/{client_id}/events")
            for event in reversed(events):
                stamp = datetime.fromisoformat(event["created_at"]).strftime("%d %b · %H:%M:%S")
                with st.container(border=True):
                    st.caption(f"{stamp}  ·  {event['event_type']}")
                    if event["event_type"] == "WEBHOOK_TRIGGERED":
                        st.write("Simulated downstream handoff")
                        st.code(event["description"], language="json", wrap_lines=True)
                    else:
                        st.write(event["description"])

st.divider()
st.caption("FICTIONAL DATA ONLY · Software-engineering demonstration. Not intended for real KYC, AML, compliance, or financial decisions.")
