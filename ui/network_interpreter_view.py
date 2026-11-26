import streamlit as st
from core.ai_client import AIClient
from core.cheat_sheet_exporter import record_study_note
from core.network_command_analyzer import (
    analyze_command_input,
    format_command_report_markdown,
)

SAMPLE_COMMANDS = {
    "Traceroute (Latency Spike + Gateway Timeout)": """$ traceroute gw.dalmedica.com
tracing route to gw.dalmedica.com (204.70.10.246), 30 hops max
1 gw1.enterisp.net (211.198.12.30) 5.412ms 5.112ms 5.613ms
2 core1.enterisp.net (211.197.22.15) 30.160ms 34.576ms 34.180ms
3 core2.enterisp.net (210.105.60.17) 770.433ms 890.899ms 920.891ms
4 gw.Dalmedica.com (204.70.10.246) * * * Request timed out.""",
    "Nmap Service & Version Scan": """$ nmap -sV -p 22,80,443 scanme.nmap.org
Starting Nmap 7.94 ( https://nmap.org )
PORT    STATE SERVICE VERSION
22/tcp  open  ssh     OpenSSH 8.2p1 Ubuntu
80/tcp  open  http    Apache httpd 2.4.41
443/tcp filtered https""",
    "Linux File Permissions Hardening": """$ chmod 700 ~/.ssh && ls -ld ~/.ssh
drwx------ 2 meddie meddie 4096 Nov 26 15:30 /home/meddie/.ssh""",
}

ETHICAL_HACKER_MENTOR_PROMPT = """
You are a practical ethical hacking and defensive security mentor helping a learner understand what they are doing.
Explain clearly and concisely:
1. **Command Mechanics & Intent:** What the command/flags do and what information an ethical hacker is trying to gather or verify.
2. **Reading the Output & Traps:** What stands out in the output (such as latency jumps, timeouts, filtered ports, or permission masks) and common misinterpretations.
3. **Authorized Scope & Safer Next Steps:** Remind the user to stay strictly within authorized scope, note any noise/risk trade-offs, and give 2 concrete follow-up checks.
"""


def render_network_interpreter_view():
    st.header("🛡️ Ethical Hacking Command & Output Interpreter")
    st.caption(
        "Understand what any command or terminal output means—recon, routing, web/DNS, sockets, or host hardening—before jumping to conclusions."
    )

    preset_choice = st.selectbox(
        "Load a sample command/output (or edit freely below):",
        ["Custom / Current"] + list(SAMPLE_COMMANDS.keys()),
        key="cmd_interp_preset",
    )

    if "cmd_interp_text" not in st.session_state:
        st.session_state["cmd_interp_text"] = SAMPLE_COMMANDS["Traceroute (Latency Spike + Gateway Timeout)"]

    if preset_choice != "Custom / Current" and st.button("📥 Load Sample", key="cmd_load_sample_btn"):
        st.session_state["cmd_interp_text"] = SAMPLE_COMMANDS[preset_choice]
        st.session_state.pop("cmd_last_ai_insight", None)
        st.rerun()

    raw_output = st.text_area(
        "Command and/or Terminal Output:",
        height=190,
        key="cmd_interp_text",
    )

    c1, c2 = st.columns([1.3, 1.5])
    with c1:
        interpret_clicked = st.button("🔎 Break Down Command", type="primary", use_container_width=True, key="cmd_parse_btn")
    with c2:
        deep_ai_clicked = st.button("🧠 Ethical Hacker Deep Dive & Save Note", use_container_width=True, key="cmd_ai_btn")

    if not raw_output.strip():
        st.info("Paste a command, terminal output, or both above to inspect what it does.")
        return

    analysis = analyze_command_input(raw_output)

    m1, m2, m3 = st.columns(3)
    m1.metric("Category", analysis["family"])
    m2.metric("Flag / Arg Notes", len(analysis["flag_notes"]))
    m3.metric("Output Signals", len(analysis["findings"]))

    st.markdown("### 🎯 Purpose & Mechanics")
    st.write(analysis["overview"])

    if analysis["flag_notes"]:
        st.markdown("### 🧩 Flags & Arguments")
        for flag_note in analysis["flag_notes"]:
            st.markdown(f"- {flag_note}")

    if analysis["findings"]:
        st.markdown("### ⚠️ Output Signals & Interpretation")
        for finding in analysis["findings"]:
            st.warning(finding)

    tr = analysis.get("traceroute")
    if tr and tr.get("hops"):
        st.markdown("### 📊 Traceroute Hop Breakdown")
        table_rows = [
            {
                "Hop": h["hop"],
                "Host": h["hostname"],
                "IP": h["ip"],
                "Samples (ms)": ", ".join(str(x) for x in h["rtts_ms"]) if h["rtts_ms"] else "* * *",
                "Avg (ms)": h["avg_ms"] if h["avg_ms"] is not None else "Timeout",
                "Delta (ms)": f"+{h['delta_ms']}" if h["delta_ms"] is not None else "-",
            }
            for h in tr["hops"]
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

    ai_text = st.session_state.get("cmd_last_ai_insight", "")
    if deep_ai_clicked:
        with st.spinner("Analyzing command mechanics, edge cases, and safe next steps..."):
            ai = AIClient()
            prompt = (
                f"Detected Command: {analysis['command_line']}\n"
                f"Detected Category: {analysis['family']}\n"
                f"Findings: {analysis['findings']}\n\n"
                f"Raw Input:\n{raw_output}"
            )
            ai_text = ai.ask(prompt, system_instruction=ETHICAL_HACKER_MENTOR_PROMPT)
            st.session_state["cmd_last_ai_insight"] = ai_text
            note_title = f"CLI Analysis: {analysis['command_line'][:55]}"
            report_md = format_command_report_markdown(analysis, raw_output, ai_insight=ai_text)
            record_study_note(
                source="Ethical Hacking Interpreter",
                title=note_title,
                explanation=report_md,
                command=analysis["command_line"] if analysis["command_line"].startswith("(") is False else raw_output,
                command_notes="Captured command mechanics, output signals, and authorized next steps.",
            )
            st.toast("Saved command breakdown to your session cheat-sheet!")

    if interpret_clicked or ai_text:
        st.markdown("### 📋 Guardrails & Next Steps")
        for guard in analysis["safety_notes"]:
            st.markdown(f"- **Scope / Safety:** {guard}")
        for step in analysis["next_steps"]:
            st.markdown(f"- **Next Check:** {step}")
        if ai_text:
            st.markdown("### 🧠 Deep Mentor Walkthrough")
            st.markdown(ai_text)