(function () {
    "use strict";

    function todayFromServer() {
        const raw = window.ADMIN_LOCAL_DATE;
        if (typeof raw === "string" && /^\d{4}-\d{2}-\d{2}$/.test(raw)) {
            const parts = raw.split("-");
            return new Date(
                Number(parts[0]),
                Number(parts[1]) - 1,
                Number(parts[2]),
                12,
                0,
                0,
            );
        }
        return new Date();
    }

    if (window.CalendarNamespace) {
        CalendarNamespace.serverToday = todayFromServer;

        const originalDraw = CalendarNamespace.draw;
        CalendarNamespace.draw = function (month, year, div_id, callback, selected) {
            originalDraw(month, year, div_id, callback, selected);
            const calDiv = document.getElementById(div_id);
            if (!calDiv) {
                return;
            }
            const caption = calDiv.querySelector("caption");
            if (!caption) {
                return;
            }

            const monthNum = parseInt(month, 10);
            const yearNum = parseInt(year, 10);
            caption.textContent = "";
            caption.classList.add("calendar-caption-nav");

            const monthSelect = document.createElement("select");
            monthSelect.className = "calendar-month-select";
            monthSelect.setAttribute("aria-label", "Mês");
            CalendarNamespace.monthsOfYear.forEach(function (name, idx) {
                const opt = document.createElement("option");
                opt.value = String(idx + 1);
                opt.textContent = name;
                if (idx + 1 === monthNum) {
                    opt.selected = true;
                }
                monthSelect.appendChild(opt);
            });

            const yearSelect = document.createElement("select");
            yearSelect.className = "calendar-year-select";
            yearSelect.setAttribute("aria-label", "Ano");
            const startYear = yearNum - 100;
            const endYear = yearNum + 10;
            for (let y = startYear; y <= endYear; y++) {
                const opt = document.createElement("option");
                opt.value = String(y);
                opt.textContent = String(y);
                if (y === yearNum) {
                    opt.selected = true;
                }
                yearSelect.appendChild(opt);
            }

            function applyNav() {
                if (!window.DateTimeShortcuts) {
                    return;
                }
                const cal = DateTimeShortcuts.calendars.find(function (item) {
                    return item.div_id === div_id;
                });
                if (!cal) {
                    return;
                }
                cal.drawDate(
                    parseInt(monthSelect.value, 10),
                    parseInt(yearSelect.value, 10),
                    cal.selected,
                );
            }

            monthSelect.addEventListener("change", applyNav);
            yearSelect.addEventListener("change", applyNav);
            caption.appendChild(monthSelect);
            caption.appendChild(yearSelect);
        };
    }

    if (window.DateTimeShortcuts) {
        DateTimeShortcuts.now = todayFromServer;
    }
})();
