/**
 * Utsav Planner - Frontend interactions and API client.
 * Vanilla JavaScript adhering to CSP (no inline scripts).
 */
document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("plan-form");
    const resultSection = document.getElementById("result-section");
    const spinner = document.getElementById("loading-spinner");
    const display = document.getElementById("plan-display");
    const submitBtn = document.getElementById("submit-btn");

    // Set default date to 30 days in future if not populated
    const dateInput = document.getElementById("event_date");
    if (dateInput && !dateInput.value) {
        const futureDate = new Date();
        futureDate.setDate(futureDate.getDate() + 30);
        dateInput.value = futureDate.toISOString().split("T")[0];
    }

    if (!form) return;

    form.addEventListener("submit", async (e) => {
        e.preventDefault();

        const formData = new FormData(form);
        const payload = {
            event_type: formData.get("event_type"),
            event_date: formData.get("event_date"),
            city: formData.get("city"),
            guest_count: parseInt(formData.get("guest_count"), 10),
            total_budget_inr: parseInt(formData.get("total_budget_inr"), 10),
            theme: formData.get("theme") || null,
            dietary: formData.get("dietary") || null,
            notes: formData.get("notes") || null,
            language: formData.get("language") || "en",
        };

        resultSection.classList.remove("hidden");
        spinner.classList.remove("hidden");
        display.innerHTML = "";
        submitBtn.disabled = true;

        try {
            const response = await fetch("/api/plan", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(payload),
            });

            const data = await response.json();

            if (!response.ok) {
                const message = data.detail || (data.errors ? JSON.stringify(data.errors) : "Failed to generate plan");
                display.innerHTML = `<div class="error-box" role="alert"><p><strong>Error:</strong> ${message}</p></div>`;
                return;
            }

            // Render plan summary
            display.innerHTML = `
                <div class="plan-card">
                    <h3>Your Personalized Event Plan</h3>
                    <p>Budget Items: ${data.budget ? data.budget.length : 0}</p>
                    <p>Timeline Milestones: ${data.timeline ? data.timeline.length : 0}</p>
                    <a href="/api/plan/ics" class="btn btn-primary" download="timeline.ics">Download Calendar (.ics)</a>
                </div>
            `;
        } catch {
            display.innerHTML = `<div class="error-box" role="alert"><p>A network error occurred. Please try again.</p></div>`;
        } finally {
            spinner.classList.add("hidden");
            submitBtn.disabled = false;
        }
    });
});
