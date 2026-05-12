import streamlit as st
import streamlit.components.v1 as components
from rapidfuzz import fuzz
import json
import db

VISIBLE_PHASE_TYPES = ("alphabet", "words", "phrases", "phrases_reverse")
AUDIO_TYPES = ("words", "phrases")  # phase types that play audio when audio mode is on

# Short theme labels per (level, part_num). Surfaced in the sidebar group header.
PART_THEMES = {
    ("A0", 1): "Essentials",
    ("A0", 2): "Daily Words",
    ("A0", 3): "People & Verbs",
    ("A0", 4): "Prepositions",
    ("A1", 1): "Foundations",
    ("A1", 2): "Food & Home",
    ("A1", 3): "Foundations",
    ("A1", 4): "Calendar",
    ("A1", 5): "Adverbs",
    ("A1", 6): "Motion Verbs",
    ("A1", 7): "Action Verbs",
    ("A1", 8): "Foundations",
    ("A1", 9): "Household",
    ("A1", 10): "Conjunctions",
    ("A1", 11): "Family & Time",
    ("A1", 12): "Foundations",
    ("A2", 1): "Body & Health",
    ("A2", 2): "Nature & Family",
    ("A2", 3): "Study & Work",
    ("A2", 4): "Shopping",
    ("A2", 5): "Communication",
    ("A2", 6): "Time",
    ("A2", 7): "Character",
    ("A2", 8): "Daily Verbs",
    ("A2", 9): "Places",
    ("A2", 10): "Travel & Art",
    ("A2", 11): "Arts & Sport",
    ("A2", 12): "Science",
    ("A2", 13): "Society",
    ("A2", 14): "Adjectives I",
    ("A2", 15): "Adjectives II",
    ("A2", 16): "School",
    ("A2", 17): "University",
    ("A2", 18): "Professions",
    ("A2", 19): "Workplace",
    ("A2", 20): "Finance",
    ("A2", 21): "Transport",
    ("A2", 22): "Travel",
    ("A2", 23): "Emotions",
    ("A2", 24): "Personality",
    ("A2", 25): "Civic Life",
    ("A2", 26): "Media",
}


def autofocus(key: int = 0):
    components.html(
        f"<script>setTimeout(()=>window.parent.document.querySelectorAll('input[type=text]')[0]?.focus(),80);//{key}</script>",
        height=0,
    )


def _render_audio_player(initial_text: str):
    # Persistent audio iframe — stays mounted across fragment reruns so that
    # the user's first tap unlocks speechSynthesis for the iframe's lifetime
    # (required by iOS Safari). Subsequent questions push their text in via
    # localStorage events, enabling autoplay without a fresh tap.
    components.html(f"""
        <div style="margin: 20px 0;">
            <button id="playBtn" style="
                background-color: #FF4B4B;
                color: white;
                border: none;
                padding: 15px 20px;
                border-radius: 8px;
                cursor: pointer;
                font-size: 18px;
                font-weight: 600;
                width: 100%;
                box-shadow: 0 2px 8px rgba(255,75,75,0.3);
                transition: all 0.2s;
            ">
                ▶️ Play Audio
            </button>
        </div>
        <script>
        (function() {{
            let currentText = {json.dumps(initial_text)};
            let unlocked = false;
            const btn = document.getElementById('playBtn');

            const speak = (t) => {{
                if (!t) return;
                try {{
                    window.speechSynthesis.cancel();
                    const u = new SpeechSynthesisUtterance(t);
                    u.lang = 'ru-RU';
                    u.rate = 0.85;
                    window.speechSynthesis.speak(u);
                }} catch (e) {{}}
            }};

            const setReplayMode = () => {{
                unlocked = true;
                btn.textContent = '🔁 Play Again';
                btn.style.backgroundColor = '#262730';
                btn.style.boxShadow = 'none';
            }};

            btn.addEventListener('click', (e) => {{
                e.preventDefault();
                speak(currentText);
                if (!unlocked) setReplayMode();
            }});

            // Cross-frame: writer iframe in fragment writes localStorage,
            // event fires here because we're a different Window.
            window.addEventListener('storage', (e) => {{
                if (e.key !== 'russian_audio_text' || !e.newValue) return;
                try {{
                    const data = JSON.parse(e.newValue);
                    if (data.text === currentText) return;
                    currentText = data.text;
                    if (unlocked) speak(currentText);
                }} catch (err) {{}}
            }});

            btn.addEventListener('mouseover', () => {{
                btn.style.backgroundColor = unlocked ? '#3d3d4a' : '#ff5e5e';
            }});
            btn.addEventListener('mouseout', () => {{
                btn.style.backgroundColor = unlocked ? '#262730' : '#FF4B4B';
            }});
        }})();
        </script>
    """, height=80)


def _push_audio_text(text: str, counter: int):
    # Invisible writer iframe — runs inside the fragment, writes the current
    # question's text to localStorage. The persistent audio iframe (different
    # Window, same origin) receives a `storage` event and speaks the text.
    components.html(f"""
        <script>
        try {{
            localStorage.setItem('russian_audio_text', JSON.stringify({{
                text: {json.dumps(text)},
                counter: {counter}
            }}));
        }} catch (e) {{}}
        </script>
    """, height=0)


# ── Answer checking ──────────────────────────────────────────────────────────

def check_answer(user_input: str, correct: str, alts: list[str]) -> bool:
    user = user_input.strip().lower()
    if not user:
        return False
    all_accepted = [correct.lower()] + [a.lower() for a in alts]
    return any(fuzz.WRatio(user, a) >= 80 for a in all_accepted)


# ── Views ────────────────────────────────────────────────────────────────────

def show_home():
    phase = db.get_current_phase()

    if not phase:
        st.title("All Phases Complete!")
        st.balloons()
        st.success("You have graduated from every phase. Impressive.")
        return

    # Display title with part indicator for A0 phases
    title = phase["name"]
    if phase["level"] == "A0" and "Part" in phase["name"]:
        # Extract part number and add total
        import re
        match = re.search(r'Part (\d+)', phase["name"])
        if match:
            part_num = match.group(1)
            title = phase["name"].replace(f"Part {part_num}", f"Part {part_num} of 4")

    st.title(title)

    stats = db.get_phase_stats(phase["id"])
    grad = db.get_graduation_status(phase["id"])

    if st.button("Start Quiz", type="primary" if not grad["can_graduate"] else "secondary", use_container_width=True, key="start_quiz_top"):
        items = db.get_quiz_items(phase["id"])
        if not items:
            st.warning("No items available.")
            return
        st.session_state.update({
            "view": "quiz",
            "quiz_phase_id": phase["id"],
            "quiz_phase_type": phase["type"],
            "quiz_items": items,
            "quiz_index": 0,
            "quiz_results": [],
        })
        st.rerun()

    st.divider()

    col1, col2, col3 = st.columns(3)
    col1.metric("Mastered ✓", stats["mastered"])
    col2.metric("In Review ↻", stats["review"])
    col3.metric("Unseen ○", stats["unseen"])

    st.divider()
    st.subheader("Graduation Progress")

    col1, col2 = st.columns(2)
    with col1:
        acc_pct = grad["accuracy"]
        st.metric("Accuracy (last 100)", f"{acc_pct:.2%}", help="Need 85% over last 100 answers")
        st.progress(min(acc_pct, 1.0), text="85% needed")
    with col2:
        cov_pct = grad["coverage"]
        st.metric("Coverage", f"{cov_pct:.2%}", help="Need 50% answered correctly at least once")
        st.progress(min(cov_pct, 1.0), text="50% needed")

    if grad["total_seen"] > 0:
        st.caption(
            f"{grad['total_correct']} correct in last {grad['total_seen']} answers — "
            f"{grad['covered']}/{grad['total_items']} items covered"
        )

    st.divider()

    if grad["can_graduate"]:
        st.success("You've met the graduation requirements!")
        if st.button("Advance to Next Phase →", type="primary", use_container_width=True):
            db.advance_phase()
            st.rerun()
        st.write("")

    available = stats["review"] + stats["unseen"]
    if available == 0 and stats["mastered"] == phase["total_items"] and not grad["can_graduate"]:
        st.info("All items mastered but accuracy threshold not met. Keep quizzing to build your score.")


@st.fragment
def quiz_question_fragment():
    """Fragment for quiz interaction - only reruns this part on answer submission."""
    items = st.session_state.get("quiz_items", [])
    index = st.session_state.get("quiz_index", 0)
    phase_type = st.session_state.get("quiz_phase_type", "")

    if index >= len(items):
        db.save_quiz_result(st.session_state["quiz_phase_id"], st.session_state["quiz_results"])
        st.session_state["view"] = "results"
        st.rerun()
        return

    item = items[index]

    # Reset revealed state when question changes
    if st.session_state.get("quiz_revealed_for") != index:
        st.session_state["quiz_revealed"] = False
        st.session_state["quiz_revealed_for"] = index

    revealed = st.session_state.get("quiz_revealed", False)
    audio_mode = st.session_state.get("audio_mode", True)
    is_audio_quiz = audio_mode and (phase_type in AUDIO_TYPES)

    if is_audio_quiz:
        if not revealed:
            # Push the current text to the persistent audio player (rendered in show_quiz).
            _push_audio_text(item['prompt'], index)
        else:
            st.markdown(f"## {item['prompt']}")
    else:
        # Regular quiz: show Russian text
        st.markdown(f"## {item['prompt']}")
        if item.get("example"):
            st.markdown(f"<p style='font-size:1.1rem;color:#444'>{item['example']}</p>", unsafe_allow_html=True)

    if revealed:
        st.markdown(f"**{item['answer']}**")
        if item.get("example_translation"):
            st.caption(f"*{item['example_translation']}*")
        st.text_input("English translation", value="", disabled=True, label_visibility="collapsed")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Skip →", type="primary", use_container_width=True):
                st.session_state["quiz_results"].append({
                    "item_id": item["id"],
                    "prompt": item["prompt"],
                    "correct_answer": item["answer"],
                    "user_answer": "",
                    "is_correct": False,
                })
                st.session_state["quiz_index"] += 1
                st.rerun(scope="fragment")
        with col2:
            if st.button("Quit Quiz", use_container_width=True):
                st.session_state["view"] = "home"
                st.rerun()
    else:
        with st.form(key=f"q_{index}"):
            user_input = st.text_input(
                "English translation",
                placeholder="Type your answer",
                label_visibility="collapsed",
            )
            submitted = st.form_submit_button("Submit", type="primary", use_container_width=True)

        if submitted:
            is_correct = check_answer(user_input, item["answer"], item.get("alt_answers", []))
            st.session_state["quiz_results"].append({
                "item_id": item["id"],
                "prompt": item["prompt"],
                "correct_answer": item["answer"],
                "user_answer": user_input,
                "is_correct": is_correct,
            })
            st.session_state["quiz_index"] += 1
            st.rerun(scope="fragment")

        autofocus(index)

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Reveal", use_container_width=True):
                st.session_state["quiz_revealed"] = True
                st.rerun(scope="fragment")
        with col2:
            if st.button("Quit Quiz", use_container_width=True):
                st.session_state["view"] = "home"
                st.rerun()


def show_quiz():
    """Main quiz view - displays progress and calls the interactive fragment."""
    items = st.session_state.get("quiz_items", [])
    index = st.session_state.get("quiz_index", 0)
    phase_type = st.session_state.get("quiz_phase_type", "")
    audio_mode = st.session_state.get("audio_mode", True)
    is_audio_quiz = audio_mode and (phase_type in AUDIO_TYPES)

    total = len(items)

    # These don't need to rerun on every answer submission
    st.title("Quiz" + (" - Listening" if is_audio_quiz else ""))
    st.progress(index / total)
    st.caption(f"Question {index + 1} of {total}")

    # Persistent audio player — sits outside the fragment so it survives
    # fragment-scoped reruns. The fragment pushes new text into it via
    # localStorage on each question change.
    if is_audio_quiz and index < total:
        _render_audio_player(items[index]["prompt"])

    # Call the fragment - only this part reruns on answer submission
    quiz_question_fragment()


def show_results():
    results = st.session_state.get("quiz_results", [])
    if not results:
        st.session_state["view"] = "home"
        st.rerun()
        return

    correct = sum(1 for r in results if r["is_correct"])
    total = len(results)
    accuracy = correct / total

    st.title("Results")
    st.metric("Score", f"{correct} / {total}", delta=f"{accuracy:.2%}")
    st.divider()

    item_progress = db.get_items_progress([r["item_id"] for r in results])
    for r in results:
        user_ans = r["user_answer"] or "(blank)"
        prog = item_progress.get(r["item_id"], {})
        acc = prog.get("accuracy")
        seen = prog.get("times_seen", 0)
        flag = " *" if (acc is not None and acc < 0.5 and seen >= 1) else ""
        if r["is_correct"]:
            st.success(f"✓  **{r['prompt']}**{flag} = {r['correct_answer']}   *(you: {user_ans})*")
        else:
            st.error(f"✗  **{r['prompt']}**{flag} = {r['correct_answer']}   *(you: {user_ans})*")

    phase_id = st.session_state.get("quiz_phase_id")
    if phase_id:
        grad = db.get_graduation_status(phase_id)
        st.divider()
        st.subheader("Graduation Progress")
        col1, col2 = st.columns(2)
        col1.metric("Accuracy (last 100)", f"{grad['accuracy']:.2%}", help="Need 85% over last 100 answers")
        col2.metric("Coverage", f"{grad['coverage']:.2%}", help="Need 50%")
        if grad["can_graduate"]:
            st.success("Ready to graduate! Go to Home to advance.")

    components.html("""<script>
        if (window._qaHandler) window.parent.document.removeEventListener('keydown', window._qaHandler);
        window._qaHandler = function(e) {
            if (e.key === 'Enter') {
                const btns = window.parent.document.querySelectorAll('button');
                for (const btn of btns) { if (btn.innerText.trim() === 'Quiz Again') { btn.click(); break; } }
            }
        };
        window.parent.document.addEventListener('keydown', window._qaHandler);
    </script>""", height=0)

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Back to Home", use_container_width=True):
            st.session_state["view"] = "home"
            st.rerun()
    with col2:
        if st.button("Quiz Again", type="primary", use_container_width=True):
            phase = db.get_current_phase()
            if phase:
                items = db.get_quiz_items(phase["id"])
                st.session_state.update({
                    "view": "quiz",
                    "quiz_phase_id": phase["id"],
                    "quiz_phase_type": phase["type"],
                    "quiz_items": items,
                    "quiz_index": 0,
                    "quiz_results": [],
                })
                st.rerun()


def _show_items_table(phase_id: int):
    items = db.get_phase_items_progress(phase_id)
    if not items:
        return
    st.divider()
    rows = []
    for it in items:
        acc = it["accuracy"]
        flag = " *" if (acc is not None and acc < 0.5 and it["times_seen"] >= 1) else ""
        rows.append({
            "Prompt": it["prompt"] + flag,
            "Answer": it["answer"],
            "Seen": it["times_seen"],
            "Correct": it["times_correct"],
            "Accuracy": round(acc * 100, 2) if acc is not None else None,
            "Status": it["status"],
        })
    st.dataframe(
        rows,
        column_config={"Accuracy": st.column_config.NumberColumn(format="%.2f%%")},
        use_container_width=True,
        hide_index=True,
    )


def show_progress():
    st.title("All Phases")

    phases = [p for p in db.get_all_phases() if p["type"] in VISIBLE_PHASE_TYPES]
    current = db.get_current_phase()
    current_id = current["id"] if current else None

    for phase in phases:
        if phase["completed"]:
            label = f"✓ {phase['name']}"
        elif phase["id"] == current_id:
            label = f"→ {phase['name']} (current)"
        else:
            label = f"○ {phase['name']}"

        with st.expander(label, expanded=(phase["id"] == current_id)):
            if phase["completed"]:
                st.success("Completed")
                _show_items_table(phase["id"])
            elif phase["id"] == current_id:
                stats = db.get_phase_stats(phase["id"])
                grad = db.get_graduation_status(phase["id"])
                col1, col2, col3 = st.columns(3)
                col1.metric("Mastered", stats["mastered"])
                col2.metric("In Review", stats["review"])
                col3.metric("Unseen", stats["unseen"])
                st.write(f"Accuracy (last 100): **{grad['accuracy']:.2%}** / 85% needed")
                st.write(f"Coverage: **{grad['coverage']:.2%}** / 50% needed")
                _show_items_table(phase["id"])
            else:
                st.caption("Locked — complete current phase to unlock")

    st.divider()
    st.subheader("Recent Quizzes")
    history = db.get_quiz_history(limit=20)
    if history:
        for s in history:
            st.write(
                f"`{s['date']}` &nbsp; {s['phase_name']} &nbsp; "
                f"**{s['correct']}/{s['items_quizzed']}** ({s['accuracy']:.2%})"
            )
    else:
        st.caption("No quizzes yet.")


def show_unlock():
    phase_id = st.session_state.get("unlocking_phase_id")
    if not phase_id:
        st.session_state["view"] = "home"
        st.rerun()
        return

    phase_name = st.session_state.get("unlocking_phase_name", "")
    type_label = st.session_state.get("unlocking_phase_type_label", "")
    title = f"{phase_name} — {type_label}" if type_label else phase_name

    st.title("🔒 Locked Phase")
    st.write(f"**{title}**")
    st.caption("Enter the password to unlock this phase early.")

    with st.form(key="unlock_form"):
        password = st.text_input("Password", type="password")
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Unlock", type="primary", use_container_width=True)
        with col2:
            cancel = st.form_submit_button("Cancel", use_container_width=True)

    if cancel:
        st.session_state["view"] = "home"
        st.rerun()
    elif submitted:
        if db.unlock_phase(phase_id, password):
            db.set_current_phase(phase_id)
            st.session_state["view"] = "home"
            st.session_state.pop("unlocking_phase_id", None)
            st.session_state.pop("unlocking_phase_name", None)
            st.session_state.pop("unlocking_phase_type_label", None)
            st.rerun()
        else:
            st.error("Incorrect password")


# ── PWA Support ──────────────────────────────────────────────────────────────

def inject_pwa_support():
    """Inject PWA manifest link and service worker registration."""
    components.html("""
        <script>
            // Register service worker for offline support
            if ('serviceWorker' in navigator) {
                navigator.serviceWorker.register('/service-worker.js')
                    .then(reg => console.log('Service Worker registered', reg))
                    .catch(err => console.log('Service Worker registration failed', err));
            }

            // Add manifest link to head
            const manifestLink = document.createElement('link');
            manifestLink.rel = 'manifest';
            manifestLink.href = '/manifest.json';
            document.head.appendChild(manifestLink);

            // Add PWA meta tags
            const metaTheme = document.createElement('meta');
            metaTheme.name = 'theme-color';
            metaTheme.content = '#FF4B4B';
            document.head.appendChild(metaTheme);

            const metaViewport = document.querySelector('meta[name="viewport"]');
            if (!metaViewport) {
                const viewport = document.createElement('meta');
                viewport.name = 'viewport';
                viewport.content = 'width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no';
                document.head.appendChild(viewport);
            }
        </script>
    """, height=0)


# ── Sidebar + routing ────────────────────────────────────────────────────────

def main():
    st.set_page_config(page_title="Russian Learning", layout="centered")

    # Inject PWA support once per session
    if "pwa_injected" not in st.session_state:
        inject_pwa_support()
        st.session_state["pwa_injected"] = True

    # Only initialize DB once per session, not on every rerun
    if "db_initialized" not in st.session_state:
        db.init_db()
        st.session_state["db_initialized"] = True

    if "view" not in st.session_state:
        st.session_state["view"] = "home"

    with st.sidebar:
        st.markdown("## Russian Learning")
        if st.button("Home", use_container_width=True):
            st.session_state["view"] = "home"
            st.rerun()
        if st.button("Progress", use_container_width=True):
            st.session_state["view"] = "progress"
            st.rerun()

        st.divider()

        if "audio_mode" not in st.session_state:
            st.session_state["audio_mode"] = True
        st.toggle(
            "Audio mode",
            key="audio_mode",
            help="When on, Words and Phrases prompts play audio instead of showing Russian text.",
        )

        st.divider()
        st.markdown("### Phases")

        current = db.get_current_phase()
        current_id = current["id"] if current else None
        all_phases = [p for p in db.get_all_phases() if p["type"] in VISIBLE_PHASE_TYPES]

        # Group phases by level and part
        phase_groups = {}

        for phase in all_phases:
            if phase["level"] == "alphabet":
                key = "Alphabet"
            elif phase["level"] in ["A0", "A1", "A2"]:
                # Extract part number from name
                import re
                match = re.search(r'Part (\d+)', phase["name"])
                if match:
                    part_num = int(match.group(1))
                    theme = PART_THEMES.get((phase['level'], part_num))
                    key = f"{phase['level']} Part {part_num}"
                    if theme:
                        key = f"{key} — {theme}"
                else:
                    key = phase["level"]
            else:
                key = phase["level"]

            if key not in phase_groups:
                phase_groups[key] = []
            phase_groups[key].append(phase)

        for group_name, phases in phase_groups.items():
            if not phases:
                continue

            with st.expander(group_name, expanded=(any(p["id"] == current_id for p in phases))):
                for phase in phases:
                    grad = db.get_graduation_status(phase["id"])
                    is_locked = db.is_phase_locked(phase["id"])

                    # Determine icon and button type
                    if is_locked:
                        icon = "🔒"
                        btn_type = "secondary"
                    elif phase["completed"]:
                        icon = "✅"
                        btn_type = "secondary"
                    elif grad["can_graduate"]:
                        icon = "✓"
                        btn_type = "secondary"
                    elif phase["id"] == current_id:
                        icon = "→"
                        btn_type = "primary"
                    else:
                        icon = "○"
                        btn_type = "secondary"

                    type_map = {
                        "words": "Words",
                        "phrases": "Phrases",
                        "phrases_reverse": "Phrases (En→Ru)",
                        "alphabet": "",
                    }
                    type_label = type_map.get(phase["type"], phase["type"])
                    label = f"{icon} {type_label}" if type_label else f"{icon} {phase['name']}"

                    if st.button(label, key=f"nav_{phase['id']}", use_container_width=True, type=btn_type):
                        if is_locked:
                            st.session_state["unlocking_phase_id"] = phase["id"]
                            st.session_state["unlocking_phase_name"] = phase["name"]
                            st.session_state["unlocking_phase_type_label"] = type_label
                            st.session_state["view"] = "unlock"
                        else:
                            db.set_current_phase(phase["id"])
                            st.session_state["view"] = "home"
                        st.rerun()

        st.divider()
        if not st.session_state.get("confirm_reset"):
            if st.button("Reset all progress", use_container_width=True):
                st.session_state["confirm_reset"] = True
                st.rerun()
        else:
            st.warning("This will erase all progress, history, and unlocks. Are you sure?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, reset", type="primary", use_container_width=True):
                    db.reset_all_progress()
                    for k in ["confirm_reset", "quiz_items", "quiz_index", "quiz_results",
                              "quiz_phase_id", "quiz_phase_type", "quiz_revealed",
                              "quiz_revealed_for"]:
                        st.session_state.pop(k, None)
                    st.session_state["view"] = "home"
                    st.rerun()
            with c2:
                if st.button("Cancel", use_container_width=True):
                    st.session_state["confirm_reset"] = False
                    st.rerun()

    view = st.session_state["view"]
    if view == "home":
        show_home()
    elif view == "quiz":
        show_quiz()
    elif view == "results":
        show_results()
    elif view == "progress":
        show_progress()
    elif view == "unlock":
        show_unlock()


if __name__ == "__main__":
    main()
