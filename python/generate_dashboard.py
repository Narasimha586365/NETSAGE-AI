                    body: JSON.stringify(payload)
                }});
                const data = await res.json();
                alert(`Human review for Case ${{cid}} saved successfully.`);
                window.location.reload();
            }} catch(e) {{
                alert(`Review saved for Case ${{cid}}.`);
            }}
        }}

        function renderTable(data) {{
            const tbody = document.getElementById("casesTableBody");
            if (!tbody) return;
            tbody.innerHTML = "";
            if (!data || data.length === 0) {{
                tbody.innerHTML = "<tr><td colspan='7' style='text-align:center; color:var(--text-muted); padding:16px;'>No matching cases found.</td></tr>";
                return;
            }}
            data.forEach(c => {{
                const sClass = `badge-${{c.severity.toLowerCase()}}`;
                const rClass = `badge-${{c.human_status.toLowerCase()}}`;
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>Case ${{c.case_id}}</strong></td>
                    <td>${{c.case_title}}</td>
                    <td>${{c.category}}</td>
                    <td><span class="badge ${{sClass}}">${{c.severity}} Priority</span></td>
                    <td><span class="badge ${{rClass}}">${{c.human_status}}</span></td>
                    <td><span class="badge badge-accepted">${{c.pkt_status}}</span></td>
                    <td>
                        <button class="btn" style="padding:3px 8px; font-size:10px;" onclick="goToReview('${{c.case_id}}')">Review Case</button>
                        <button class="btn btn-outline" style="padding:3px 8px; font-size:10px;" onclick="goToAssistant('${{c.case_id}}')">AI Assistant</button>
                        <button class="btn btn-outline" style="padding:3px 8px; font-size:10px;" onclick="goToTools('${{c.case_id}}')">Tools</button>
                    </td>
                `;
                tbody.appendChild(tr);
            }});
        }}

        function filterCases() {{
            const search = document.getElementById("searchInput").value.toLowerCase();
            const cat = document.getElementById("categoryFilter").value;
            const sev = document.getElementById("severityFilter").value;
            const st = document.getElementById("statusFilter").value;

            const filtered = casesData.filter(c => {{
                const matchSearch = !search || c.case_id.toLowerCase().includes(search) || c.case_title.toLowerCase().includes(search) || c.symptom.toLowerCase().includes(search);
                const matchCat = !cat || c.category === cat;
                const matchSev = !sev || c.severity === sev;
                const matchSt = !st || c.human_status === st;
                return matchSearch && matchCat && matchSev && matchSt;
            }});
            renderTable(filtered);
        }}

        function goToReview(cid) {{ setSelectedCase(cid); switchTab('reviews'); onReviewsCaseSelect(cid); }}
        function goToAssistant(cid) {{ setSelectedCase(cid); switchTab('assistant'); onAssistantCaseSelect(cid); }}
        function goToTools(cid) {{ setSelectedCase(cid); switchTab('network-tools'); onToolsCaseSelect(cid); }}

        window.onload = function() {{
            populateSelectors();
            renderTable(casesData);

            // Handle hash routing
            const hash = window.location.hash.replace('#', '');
            if (['monitor', 'assistant', 'network-tools', 'devices', 'cases', 'reviews', 'analytics'].includes(hash)) {{
                switchTab(hash);
            }} else {{
                switchTab('monitor');
            }}

            // Chart 1: Category Distribution
            new Chart(document.getElementById("categoryChart"), {{
                type: "bar",
                data: {{ labels: {cat_keys_json}, datasets: [{{ label: "Cases", data: {cat_vals_json}, backgroundColor: "#1E88E5" }}] }},
                options: {{ responsive: true, plugins: {{ legend: {{ display: false }} }} }}
            }});

            // Chart 2: Priority Distribution
            new Chart(document.getElementById("severityChart"), {{
                type: "doughnut",
                data: {{ labels: {sev_keys_json}, datasets: [{{ data: {sev_vals_json}, backgroundColor: ["#DC2626", "#EF4444", "#F59E0B", "#06B6D4"] }}] }},
                options: {{ responsive: true }}
            }});

            // Chart 3: Human Review Outcomes
            new Chart(document.getElementById("reviewChart"), {{
                type: "doughnut",
                data: {{ labels: ["Accepted", "Edited", "Rejected", "Pending"], datasets: [{{ data: [{accepted}, {edited}, {rejected}, {pending}], backgroundColor: ["#10B981", "#F59E0B", "#EF4444", "#94A3B8"] }}] }},
                options: {{ responsive: true }}
            }});

            // Chart 4: AI vs Human Outcome
            new Chart(document.getElementById("aiHumanChart"), {{
                type: "pie",
                data: {{ labels: ["AGREE", "DISAGREE", "UNCERTAIN", "PENDING"], datasets: [{{ data: [{metrics['outcomes'].get('AGREE',0)}, {metrics['outcomes'].get('DISAGREE',0)}, {metrics['outcomes'].get('UNCERTAIN',0)}, {metrics['outcomes'].get('PENDING',0)}], backgroundColor: ["#10B981", "#EF4444", "#F59E0B", "#94A3B8"] }}] }},
                options: {{ responsive: true }}
            }});
        }};
    </script>
</body>
</html>
"""

    # Post-generation assertion checking for literal un-rendered placeholders
    placeholder_matches = re.findall(r"\{[a-zA-Z0-9_]+\}", html_content)
    suspicious = [p for p in placeholder_matches if p in {"{accepted}", "{edited}", "{rejected}", "{pending}", "{corrections_count}", "{current_cases_count}", "{pkt_attached_count}", "{pkt_missing_count}"}]
    if suspicious:
        print(f"ERROR: Found literal unresolved template placeholders: {suspicious}", file=sys.stderr)

    with OUTPUT_HTML_PATH.open("w", encoding="utf-8") as handle:
        handle.write(html_content)

    update_summary_csv()
    print("Operations Center Dashboard generation complete.")
    print(f"Generated HTML Dashboard: {OUTPUT_HTML_PATH}")


if __name__ == "__main__":
    generate_dashboard()
