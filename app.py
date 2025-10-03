# app.py
import os
import requests
import sys
import importlib
import streamlit as st
# try:
#     import pysqlite3  # wheels import under this name
# except Exception:
#     importlib.import_module("pysqlite3")
# sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")

API_BASE = os.getenv("API_BASE", "http://localhost:8000")
TIMEOUT  = 60

st.set_page_config(page_title="Meeting Summarizer — Demo", layout="wide")
st.title("Meeting Summarizer — Demo")

# ---------------- helpers ----------------
def api_get(path: str):
    try:
        r = requests.get(f"{API_BASE}{path}", timeout=TIMEOUT)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def api_post(path: str, json_body: dict):
    try:
        r = requests.post(f"{API_BASE}{path}", json=json_body, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json(), None
    except Exception as e:
        return None, str(e)

def ensure_projects_cached(force=False):
    if force or "_projects_cache" not in st.session_state or st.session_state["_projects_cache"] is None:
        data, err = api_get("/projects")
        if err:
            st.error(f"Failed to load projects: {err}")
            st.session_state["_projects_cache"] = []
        else:
            projects = data.get("projects") if isinstance(data, dict) else data
            st.session_state["_projects_cache"] = projects or []

def load_transcripts_for(project: str, force=False):
    key = f"_transcripts_{project}"
    if force or key not in st.session_state or st.session_state[key] is None:
        data, err = api_get(f"/transcripts/{project}")
        if err or (isinstance(data, dict) and data.get("error")):
            st.error(f"Failed to load transcripts for '{project}': {err or data.get('error')}")
            st.session_state[key] = []
        else:
            if isinstance(data, dict) and "transcripts" in data:
                st.session_state[key] = data["transcripts"]
            else:
                items = data or []
                if items and isinstance(items[0], str):
                    st.session_state[key] = [
                        {"label": f.replace("meeting_","").replace(".txt",""), "filename": f}
                        for f in items
                    ]
                else:
                    st.session_state[key] = items

def delete_project(project: str) -> tuple[bool, str]:
    try:
        r = requests.delete(f"{API_BASE}/projects/{project}",
                            json={"confirm": True},
                            timeout=TIMEOUT)
        if r.status_code >= 400:
            return False, r.text
        j = r.json()
        if not j.get("ok"):
            return False, j.get("error","unknown error")
        return True, "Deleted"
    except Exception as e:
        return False, str(e)

# ---------------- sidebar ----------------
with st.sidebar:
    st.header("Server")
    st.code(API_BASE)
    if st.button("Health check"):
        data, err = api_get("/health")
        if err:
            st.error(f"Health error: {err}")
        else:
            st.success(data)

    st.markdown("---")
    page = st.radio("Go to", ["Projects & Bot", "Summaries"], index=0)

# preload projects
ensure_projects_cached()

# ======================================================
# Page 1: Projects & Bot (single selector + inline create)
# ======================================================
if page == "Projects & Bot":
    st.subheader("Select or Create Project")

    # refresh + build options list (with "create new" at end)
    if st.button("Refresh projects", key="refresh_projects_1"):
        ensure_projects_cached(force=True)

    projects = st.session_state["_projects_cache"] or []
    create_tag = "➕ Create new project…"
    options = projects + [create_tag] if projects else [create_tag]

    # remember selection across reruns
    default_index = 0
    if "selected_project" in st.session_state and st.session_state["selected_project"] in options:
        default_index = options.index(st.session_state["selected_project"])

    choice = st.selectbox("Project", options, index=default_index, key="proj_selector")

    # if user chose "Create new", show inline field + create
    if choice == create_tag:
        with st.form("inline_create_project", clear_on_submit=False):
            new_project = st.text_input("New project name")
            created = st.form_submit_button("Create project")
            if created:
                if not new_project.strip():
                    st.warning("Please enter a project name.")
                else:
                    resp, err = api_post("/create_project", {"project_name": new_project.strip()})
                    if err or (isinstance(resp, dict) and resp.get("error")):
                        st.error(f"Create project failed: {err or resp.get('error')}")
                    else:
                        st.success(f"Project created: {resp.get('project') or new_project}")
                        # refresh projects, select newly created, and rerun
                        ensure_projects_cached(force=True)
                        st.session_state["selected_project"] = new_project.strip()
                        st.rerun()
    else:
        # record selected project in session
        st.session_state["selected_project"] = choice

    st.markdown("---")
    st.subheader("Request bot to join a meeting")

    # project to use (must be a real name, not the create tag)
    effective_project = st.session_state.get("selected_project")
    if not effective_project or effective_project == create_tag:
        st.info("Select an existing project or create one above to continue.")
    else:
        with st.form("start_bot_form_single", clear_on_submit=False):
            meet_url = st.text_input("Google Meet link (meeting_url)")
            custom_bot_name = st.text_input("Bot name (optional)", value=f"{effective_project}_bot")
            submit = st.form_submit_button("Request bot")
            if submit:
                if not meet_url.strip():
                    st.warning("Please paste a meeting URL.")
                else:
                    payload = {
                        "meeting_url": meet_url.strip(),
                        "project_name": effective_project,
                        "bot_name": (custom_bot_name.strip() or f"{effective_project}_bot"),
                    }
                    resp, err = api_post("/start_bot", payload)
                    if err or (isinstance(resp, dict) and not resp.get("ok", True)):
                        st.error(f"Start bot failed: {err or resp.get('error')}")
                    else:
                        st.success(f"Bot requested for project '{resp.get('project')}'")
                        st.info("After the meeting ends and is processed, the transcript will appear under this project.")

# ======================================================
# Page 2: Summaries — single title, ⋮ on same line, aligned Refresh
# ======================================================
if page == "Summaries":
    # CSS: move the ⋮ up to the title line and keep controls tight
    st.markdown(
        """
        <style>
        /* button + select compact heights */
        div[data-baseweb="select"] > div { min-height: 38px; }
        .stButton>button { height: 38px; }

        /* put the menu on the title line (right corner) */
        .title-menu-wrap {
            display: flex; justify-content: flex-end;
            margin-top: -48px;   /* pull up into the title row */
            margin-bottom: 8px;
        }
        .title-menu-wrap button { padding: 4px 10px !important; border-radius: 8px; }

        /* align the refresh button vertically with the selectbox */
        .refresh-spacer { height: 6px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ---- tiny title-line menu (no extra "Summarizer" subheader) ----
    st.markdown('<div class="title-menu-wrap">', unsafe_allow_html=True)
    try:
        pop = st.popover("⋮")
        with pop:
            st.caption("Project actions")
            ensure_projects_cached()
            _menu_projects = st.session_state.get("_projects_cache", []) or []
            if _menu_projects:
                _del_proj = st.selectbox("Delete project", _menu_projects, key="menu_del_proj")
                if st.button("Delete", key="menu_del_btn"):
                    ok, msg = delete_project(_del_proj)
                    if ok:
                        st.success(f"Deleted '{_del_proj}'.")
                        ensure_projects_cached(force=True)
                        st.session_state.pop(f"_transcripts_{_del_proj}", None)
                        st.rerun()
                    else:
                        st.error(f"Delete failed: {msg}")
            else:
                st.info("No projects yet.")
    except Exception:
        with st.expander("⋮", expanded=False):
            st.caption("Project actions")
            ensure_projects_cached()
            _menu_projects = st.session_state.get("_projects_cache", []) or []
            if _menu_projects:
                _del_proj = st.selectbox("Delete project", _menu_projects, key="menu_del_proj_fb")
                if st.button("Delete", key="menu_del_btn_fb"):
                    ok, msg = delete_project(_del_proj)
                    if ok:
                        st.success(f"Deleted '{_del_proj}'.")
                        ensure_projects_cached(force=True)
                        st.session_state.pop(f"_transcripts_{_del_proj}", None)
                        st.rerun()
                    else:
                        st.error(f"Delete failed: {msg}")
            else:
                st.info("No projects yet.")
    st.markdown('</div>', unsafe_allow_html=True)

    # ---- main content ----
    st.markdown("---")
    ensure_projects_cached()
    projects = st.session_state["_projects_cache"] or []

    # No project? stop (prevents accidental "default" folder creation)
    if not projects:
        st.info("No projects found. Please create a project on the 'Projects & Bot' page first.")
        st.stop()

    # Row 1: Choose Project (left) + Refresh (right, aligned)
    r1c1, r1c2 = st.columns([6, 1.5])
    with r1c1:
        default_idx = 0
        if "selected_project" in st.session_state and st.session_state["selected_project"] in projects:
            default_idx = projects.index(st.session_state["selected_project"])
        chosen_proj = st.selectbox("Choose Project", projects, index=default_idx, key="proj_sel_compact")
        st.session_state["selected_project"] = chosen_proj
    with r1c2:
        st.markdown('<div class="refresh-spacer"></div>', unsafe_allow_html=True)
        refresh_clicked = st.button("Refresh", key="refresh_tx_list_btn", use_container_width=True)

    # Row 2: Transcript dropdown (auto-refresh on button)
    load_transcripts_for(chosen_proj, force=refresh_clicked)
    transcripts = st.session_state.get(f"_transcripts_{chosen_proj}") or []
    if not transcripts:
        st.info("No transcripts for this project yet.")
        st.stop()

    labels = [t["label"] for t in transcripts]
    chosen_label = st.selectbox("Choose Transcript", labels, index=0, key="tx_sel_compact")
    chosen_file = transcripts[labels.index(chosen_label)]["filename"]

    # Row 3: Get Summary
    if st.button("Get Summary", use_container_width=True):
        with st.spinner("Generating summary…"):
            resp, err = api_post("/summarize", {
                "project_name": chosen_proj,
                "transcript_file": chosen_file
            })
            if err or (isinstance(resp, dict) and resp.get("error")):
                st.error(f"Summarize failed: {err or resp.get('error')}")
            else:
                st.success("Summary ready.")
                st.markdown(resp.get("summary", ""))