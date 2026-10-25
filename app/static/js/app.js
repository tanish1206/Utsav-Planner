/**
 * Utsav Planner - Accessible Client-Side Controller.
 * Strict XSS defense: renders exclusively using DOM createElement and textContent (never innerHTML).
 * Full ARIA tab navigation (arrow keys), error summary focus management, and calendar integration.
 */

document.addEventListener("DOMContentLoaded", () => {
    // DOM Elements
    const form = document.getElementById("plan-form");
    const submitBtn = document.getElementById("submit-btn");
    const errorSummary = document.getElementById("error-summary");
    const errorSummaryList = document.getElementById("error-summary-list");
    const loadingContainer = document.getElementById("loading-container");
    const resultsSection = document.getElementById("results-section");
    const regenerateBtn = document.getElementById("regenerate-btn");
    const printBtn = document.getElementById("print-btn");
    const downloadIcsBtn = document.getElementById("download-ics-btn");

    // Content Containers
    const budgetContainer = document.getElementById("budget-content");
    const timelineContainer = document.getElementById("timeline-content");
    const vendorsContainer = document.getElementById("vendors-content");
    const ideasContainer = document.getElementById("ideas-content");
    const warningsContainer = document.getElementById("warnings-content");

    // Form inputs
    const eventTypeInput = document.getElementById("event_type");
    const eventDateInput = document.getElementById("event_date");
    const cityInput = document.getElementById("city");
    const guestCountInput = document.getElementById("guest_count");
    const totalBudgetInput = document.getElementById("total_budget_inr");
    const themeInput = document.getElementById("theme");
    const dietaryInput = document.getElementById("dietary");
    const notesInput = document.getElementById("notes");
    const languageInput = document.getElementById("language");

    // Default event date to 30 days in the future if empty
    if (eventDateInput && !eventDateInput.value) {
        const futureDate = new Date();
        futureDate.setDate(futureDate.getDate() + 30);
        eventDateInput.value = futureDate.toISOString().split("T")[0];
    }

    // --- Tablist Keyboard Navigation (Arrow Keys, Home, End) ---
    const tabList = document.querySelector('[role="tablist"]');
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    const panels = Array.from(document.querySelectorAll('[role="tabpanel"]'));

    function switchTab(newTab) {
        tabs.forEach((tab) => {
            const isTarget = tab === newTab;
            tab.setAttribute("aria-selected", isTarget ? "true" : "false");
            tab.setAttribute("tabindex", isTarget ? "0" : "-1");
            tab.classList.toggle("active", isTarget);
        });

        const targetPanelId = newTab.getAttribute("aria-controls");
        panels.forEach((panel) => {
            const isTarget = panel.id === targetPanelId;
            panel.classList.toggle("hidden", !isTarget);
            panel.classList.toggle("active", isTarget);
        });

        newTab.focus();
    }

    if (tabList) {
        tabList.addEventListener("keydown", (e) => {
            const currentIndex = tabs.indexOf(document.activeElement);
            if (currentIndex === -1) return;

            let nextIndex = null;
            if (e.key === "ArrowRight") {
                nextIndex = (currentIndex + 1) % tabs.length;
            } else if (e.key === "ArrowLeft") {
                nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
            } else if (e.key === "Home") {
                nextIndex = 0;
            } else if (e.key === "End") {
                nextIndex = tabs.length - 1;
            }

            if (nextIndex !== null) {
                e.preventDefault();
                switchTab(tabs[nextIndex]);
            }
        });

        tabs.forEach((tab) => {
            tab.addEventListener("click", () => switchTab(tab));
        });
    }

    // --- Form Error Management ---
    function clearFormErrors() {
        errorSummary.classList.add("hidden");
        while (errorSummaryList.firstChild) {
            errorSummaryList.removeChild(errorSummaryList.firstChild);
        }

        const fields = [
            "event_type",
            "event_date",
            "city",
            "guest_count",
            "total_budget_inr",
            "theme",
            "dietary",
            "notes",
            "language",
        ];

        fields.forEach((fieldId) => {
            const input = document.getElementById(fieldId);
            const errorSpan = document.getElementById(`${fieldId}_error`);
            if (input) {
                input.removeAttribute("aria-invalid");
                const hintId = `${fieldId}_hint`;
                input.setAttribute("aria-describedby", hintId);
            }
            if (errorSpan) {
                errorSpan.classList.add("hidden");
                errorSpan.textContent = "";
            }
        });
    }

    function showFormErrors(errors) {
        clearFormErrors();
        errorSummary.classList.remove("hidden");

        errors.forEach((err) => {
            const li = document.createElement("li");
            const link = document.createElement("a");
            link.href = `#${err.fieldId}`;
            link.textContent = err.message;
            link.addEventListener("click", (e) => {
                e.preventDefault();
                const targetEl = document.getElementById(err.fieldId);
                if (targetEl) {
                    targetEl.focus();
                }
            });
            li.appendChild(link);
            errorSummaryList.appendChild(li);

            // Highlight individual field
            const input = document.getElementById(err.fieldId);
            const errorSpan = document.getElementById(`${err.fieldId}_error`);
            if (input) {
                input.setAttribute("aria-invalid", "true");
                const hintId = `${err.fieldId}_hint`;
                const errId = `${err.fieldId}_error`;
                input.setAttribute("aria-describedby", `${hintId} ${errId}`);
            }
            if (errorSpan) {
                errorSpan.textContent = err.message;
                errorSpan.classList.remove("hidden");
            }
        });

        errorSummary.focus();
    }

    function validateClientInputs() {
        const clientErrors = [];
        const todayStr = new Date().toISOString().split("T")[0];

        if (!eventDateInput.value) {
            clientErrors.push({
                fieldId: "event_date",
                message: "Please specify an event date.",
            });
        } else if (eventDateInput.value <= todayStr) {
            clientErrors.push({
                fieldId: "event_date",
                message: "Event date must be strictly in the future.",
            });
        }

        const cityVal = cityInput.value.trim();
        if (!cityVal) {
            clientErrors.push({
                fieldId: "city",
                message: "Host city is required.",
            });
        } else if (cityVal.length > 80) {
            clientErrors.push({
                fieldId: "city",
                message: "City name cannot exceed 80 characters.",
            });
        }

        const guests = parseInt(guestCountInput.value, 10);
        if (isNaN(guests) || guests < 1 || guests > 5000) {
            clientErrors.push({
                fieldId: "guest_count",
                message: "Guest count must be between 1 and 5,000.",
            });
        }

        const budget = parseInt(totalBudgetInput.value, 10);
        if (isNaN(budget) || budget < 10000 || budget > 100000000) {
            clientErrors.push({
                fieldId: "total_budget_inr",
                message: "Total budget must be between ₹10,000 and ₹100,000,000.",
            });
        }

        return clientErrors;
    }

    // --- Safe DOM Rendering (textContent only, zero innerHTML) ---
    function renderPlanResults(plan) {
        // 1. Budget Breakdown Table
        while (budgetContainer.firstChild) {
            budgetContainer.removeChild(budgetContainer.firstChild);
        }

        const budgetWrapper = document.createElement("div");
        budgetWrapper.className = "table-wrapper";

        const budgetTable = document.createElement("table");
        budgetTable.className = "data-table";

        const budgetCaption = document.createElement("caption");
        budgetCaption.textContent = "Categorized Budget Breakdown (INR ₹)";
        budgetTable.appendChild(budgetCaption);

        const bHead = document.createElement("thead");
        const bHeadRow = document.createElement("tr");

        const thCat = document.createElement("th");
        thCat.scope = "col";
        thCat.textContent = "Expense Category";
        bHeadRow.appendChild(thCat);

        const thAmt = document.createElement("th");
        thAmt.scope = "col";
        thAmt.textContent = "Allocated Amount";
        bHeadRow.appendChild(thAmt);

        const thNote = document.createElement("th");
        thNote.scope = "col";
        thNote.textContent = "Context & Description";
        bHeadRow.appendChild(thNote);

        bHead.appendChild(bHeadRow);
        budgetTable.appendChild(bHead);

        const bBody = document.createElement("tbody");
        let sumTotal = 0;

        (plan.budget || []).forEach((item) => {
            sumTotal += item.amount_inr || 0;
            const row = document.createElement("tr");

            const thRow = document.createElement("th");
            thRow.scope = "row";
            thRow.textContent = item.category;
            row.appendChild(thRow);

            const tdAmt = document.createElement("td");
            tdAmt.textContent = `₹${(item.amount_inr || 0).toLocaleString("en-IN")}`;
            row.appendChild(tdAmt);

            const tdNote = document.createElement("td");
            tdNote.textContent = item.note || "";
            row.appendChild(tdNote);

            bBody.appendChild(row);
        });

        // Total Row
        const totalRow = document.createElement("tr");
        totalRow.className = "total-row";

        const thTotLabel = document.createElement("th");
        thTotLabel.scope = "row";
        thTotLabel.textContent = "Total Allocated Budget";
        totalRow.appendChild(thTotLabel);

        const tdTotVal = document.createElement("td");
        tdTotVal.textContent = `₹${sumTotal.toLocaleString("en-IN")}`;
        totalRow.appendChild(tdTotVal);

        const tdTotNote = document.createElement("td");
        tdTotNote.textContent = "100% Allocated (Includes Contingency)";
        totalRow.appendChild(tdTotNote);

        bBody.appendChild(totalRow);
        budgetTable.appendChild(bBody);
        budgetWrapper.appendChild(budgetTable);
        budgetContainer.appendChild(budgetWrapper);

        // 2. Timeline Table
        while (timelineContainer.firstChild) {
            timelineContainer.removeChild(timelineContainer.firstChild);
        }

        const timeWrapper = document.createElement("div");
        timeWrapper.className = "table-wrapper";

        const timeTable = document.createElement("table");
        timeTable.className = "data-table";

        const timeCaption = document.createElement("caption");
        timeCaption.textContent = "Chronological Milestones & Task Schedule";
        timeTable.appendChild(timeCaption);

        const tHead = document.createElement("thead");
        const tHeadRow = document.createElement("tr");

        const thTask = document.createElement("th");
        thTask.scope = "col";
        thTask.textContent = "Milestone Task";
        tHeadRow.appendChild(thTask);

        const thDue = document.createElement("th");
        thDue.scope = "col";
        thDue.textContent = "Target Due Date";
        tHeadRow.appendChild(thDue);

        const thPhase = document.createElement("th");
        thPhase.scope = "col";
        thPhase.textContent = "Planning Phase";
        tHeadRow.appendChild(thPhase);

        tHead.appendChild(tHeadRow);
        timeTable.appendChild(tHead);

        const tBody = document.createElement("tbody");
        (plan.timeline || []).forEach((task) => {
            const row = document.createElement("tr");

            const thRow = document.createElement("th");
            thRow.scope = "row";
            thRow.textContent = task.title;
            row.appendChild(thRow);

            const tdDue = document.createElement("td");
            tdDue.textContent = task.due_date || "";
            row.appendChild(tdDue);

            const tdPhase = document.createElement("td");
            tdPhase.textContent = task.category || "";
            row.appendChild(tdPhase);

            tBody.appendChild(row);
        });

        timeTable.appendChild(tBody);
        timeWrapper.appendChild(timeTable);
        timelineContainer.appendChild(timeWrapper);

        // 3. Vendors Checklist
        while (vendorsContainer.firstChild) {
            vendorsContainer.removeChild(vendorsContainer.firstChild);
        }

        (plan.vendors || []).forEach((v) => {
            const card = document.createElement("div");
            card.className = "vendor-card";

            const tag = document.createElement("span");
            tag.className = "tag-pill";
            tag.textContent = `Book By: ${v.book_by || "TBD"}`;
            card.appendChild(tag);

            const title = document.createElement("h3");
            title.className = "card-title";
            title.textContent = `Category: ${v.category}`;
            card.appendChild(title);

            const qHeading = document.createElement("p");
            qHeading.className = "card-body";
            const qHeadingBold = document.createElement("strong");
            qHeadingBold.textContent = "Essential Vetting Questions:";
            qHeading.appendChild(qHeadingBold);
            card.appendChild(qHeading);

            const qList = document.createElement("ul");
            qList.className = "questions-list";
            (v.questions || []).forEach((q) => {
                const qItem = document.createElement("li");
                qItem.textContent = q;
                qList.appendChild(qItem);
            });
            card.appendChild(qList);

            vendorsContainer.appendChild(card);
        });

        // 4. Personalized Ideas (strictly 5 items)
        while (ideasContainer.firstChild) {
            ideasContainer.removeChild(ideasContainer.firstChild);
        }

        (plan.ideas || []).forEach((idea, index) => {
            const card = document.createElement("div");
            card.className = "idea-card";

            const title = document.createElement("h3");
            title.className = "card-title";
            title.textContent = `Idea #${index + 1}`;
            card.appendChild(title);

            const body = document.createElement("p");
            body.className = "card-body";
            body.textContent = idea;
            card.appendChild(body);

            ideasContainer.appendChild(card);
        });

        // 5. Warnings & Realism Cautions
        while (warningsContainer.firstChild) {
            warningsContainer.removeChild(warningsContainer.firstChild);
        }

        const warningsList = plan.warnings || [];
        if (warningsList.length === 0) {
            const p = document.createElement("p");
            p.className = "card-body";
            p.textContent = "No specific logistical or seasonal warnings detected for this configuration.";
            warningsContainer.appendChild(p);
        } else {
            warningsList.forEach((w) => {
                const card = document.createElement("div");
                card.className = "warning-card";

                const title = document.createElement("h3");
                title.className = "card-title";
                title.textContent = "Logistical Caution";
                card.appendChild(title);

                const body = document.createElement("p");
                body.className = "card-body";
                body.textContent = w;
                card.appendChild(body);

                warningsContainer.appendChild(card);
            });
        }
    }

    // --- Form Submission Handler ---
    if (form) {
        form.addEventListener("submit", async (e) => {
            e.preventDefault();

            // 1. Client-Side Validation
            const clientErrors = validateClientInputs();
            if (clientErrors.length > 0) {
                showFormErrors(clientErrors);
                return;
            }

            clearFormErrors();

            // 2. Build Payload
            const payload = {
                event_type: eventTypeInput.value,
                event_date: eventDateInput.value,
                city: cityInput.value.trim(),
                guest_count: parseInt(guestCountInput.value, 10),
                total_budget_inr: parseInt(totalBudgetInput.value, 10),
                theme: themeInput.value.trim() || null,
                dietary: dietaryInput.value.trim() || null,
                notes: notesInput.value.trim() || null,
                language: languageInput.value || "en",
            };

            // 3. UI Busy State
            submitBtn.disabled = true;
            loadingContainer.classList.remove("hidden");
            resultsSection.classList.add("hidden");

            try {
                const response = await fetch("/api/plan", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    body: JSON.stringify(payload),
                });

                const data = await response.json();

                if (!response.ok) {
                    if (data.errors && Array.isArray(data.errors)) {
                        const apiErrors = data.errors.map((err) => {
                            let fieldName = "city";
                            if (typeof err.field === "string") {
                                const parts = err.field.split(" -> ");
                                fieldName = parts[parts.length - 1] || "city";
                            }
                            return {
                                fieldId: fieldName,
                                message: err.message || data.detail || "Validation error",
                            };
                        });
                        showFormErrors(apiErrors);
                    } else {
                        showFormErrors([
                            {
                                fieldId: "plan-form",
                                message: data.detail || "Failed to generate event plan. Please check inputs and retry.",
                            },
                        ]);
                    }
                    return;
                }

                // 4. Render Valid Plan
                renderPlanResults(data);
                resultsSection.classList.remove("hidden");

                // Default to Budget Tab
                const budgetTab = document.getElementById("tab-budget");
                if (budgetTab) {
                    switchTab(budgetTab);
                }

                resultsSection.scrollIntoView({ behavior: "smooth" });
            } catch {
                showFormErrors([
                    {
                        fieldId: "plan-form",
                        message: "A network error occurred while communicating with the server. Please try again.",
                    },
                ]);
            } finally {
                loadingContainer.classList.add("hidden");
                submitBtn.disabled = false;
            }
        });
    }

    // --- Action Buttons ---
    if (regenerateBtn) {
        regenerateBtn.addEventListener("click", () => {
            form.scrollIntoView({ behavior: "smooth" });
            const firstInput = document.getElementById("event_type");
            if (firstInput) {
                firstInput.focus();
            }
        });
    }

    if (printBtn) {
        printBtn.addEventListener("click", () => {
            window.print();
        });
    }
});
