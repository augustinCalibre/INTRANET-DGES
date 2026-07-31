document.addEventListener("DOMContentLoaded", function () {
    var themeStorageKey = "dges-theme";
    var root = document.documentElement;

    function updateThemeControls(theme) {
        document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
            button.setAttribute("aria-pressed", theme === "dark" ? "true" : "false");

            var label = button.querySelector("[data-theme-label]");
            if (label) {
                label.textContent = theme === "dark" ? "Mode clair" : "Mode sombre";
            }
        });
    }

    function setTheme(theme, persist) {
        var resolvedTheme = theme === "dark" ? "dark" : "light";
        root.setAttribute("data-theme", resolvedTheme);

        if (persist !== false) {
            try {
                localStorage.setItem(themeStorageKey, resolvedTheme);
            } catch (error) {
                // Ignore localStorage failures and keep the in-memory theme.
            }
        }

        updateThemeControls(resolvedTheme);
    }

    setTheme(root.getAttribute("data-theme") || "light", false);

    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
        button.addEventListener("click", function () {
            var currentTheme = root.getAttribute("data-theme") === "dark" ? "dark" : "light";
            setTheme(currentTheme === "dark" ? "light" : "dark");
        });
    });

    function formatCountdown(totalSeconds) {
        if (totalSeconds <= 0) {
            return "Reunion imminente";
        }

        var days = Math.floor(totalSeconds / 86400);
        var hours = Math.floor((totalSeconds % 86400) / 3600);
        var minutes = Math.floor((totalSeconds % 3600) / 60);

        if (days > 0) {
            return "Dans " + days + " j " + hours + " h";
        }
        if (hours > 0) {
            return "Dans " + hours + " h " + minutes + " min";
        }
        return "Dans " + minutes + " min";
    }

    function updateCountdowns() {
        document.querySelectorAll("[data-countdown-target]").forEach(function (element) {
            var target = element.getAttribute("data-countdown-target");
            var targetDate = target ? new Date(target) : null;

            if (!targetDate || Number.isNaN(targetDate.getTime())) {
                return;
            }

            var totalSeconds = Math.floor((targetDate.getTime() - Date.now()) / 1000);
            element.textContent = formatCountdown(totalSeconds);
        });
    }

    updateCountdowns();
    if (document.querySelector("[data-countdown-target]")) {
        window.setInterval(updateCountdowns, 60000);
    }

    function createConfirmDialog() {
        var backdrop = document.createElement("div");
        backdrop.className = "confirm-dialog-backdrop";
        backdrop.hidden = true;
        backdrop.innerHTML =
            '<div class="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirmDialogTitle" aria-describedby="confirmDialogMessage">' +
                '<div class="confirm-dialog-head">' +
                    '<div class="confirm-dialog-badge" aria-hidden="true">!</div>' +
                    '<button type="button" class="confirm-dialog-close" aria-label="Fermer la confirmation">&times;</button>' +
                "</div>" +
                '<div class="confirm-dialog-body">' +
                    '<h3 id="confirmDialogTitle" class="confirm-dialog-title">Confirmation requise</h3>' +
                    '<p id="confirmDialogMessage" class="confirm-dialog-message">Confirmer cette action ?</p>' +
                "</div>" +
                '<div class="confirm-dialog-actions">' +
                    '<button type="button" class="btn btn-outline-secondary confirm-dialog-button confirm-dialog-button-cancel">Annuler</button>' +
                    '<button type="button" class="btn btn-primary confirm-dialog-button confirm-dialog-button-confirm">Confirmer</button>' +
                "</div>" +
            "</div>";

        document.body.appendChild(backdrop);

        return {
            backdrop: backdrop,
            dialog: backdrop.querySelector(".confirm-dialog"),
            badge: backdrop.querySelector(".confirm-dialog-badge"),
            title: backdrop.querySelector(".confirm-dialog-title"),
            message: backdrop.querySelector(".confirm-dialog-message"),
            closeButton: backdrop.querySelector(".confirm-dialog-close"),
            cancelButton: backdrop.querySelector(".confirm-dialog-button-cancel"),
            confirmButton: backdrop.querySelector(".confirm-dialog-button-confirm"),
        };
    }

    var confirmDialog = createConfirmDialog();
    var confirmResolver = null;
    var previousFocusedElement = null;

    function resolveConfirmDialog(confirmed) {
        if (confirmDialog.backdrop.hidden) {
            return;
        }

        confirmDialog.backdrop.hidden = true;
        confirmDialog.dialog.classList.remove("is-danger");
        document.body.classList.remove("confirm-dialog-open");

        var resolver = confirmResolver;
        confirmResolver = null;
        if (typeof resolver === "function") {
            resolver(confirmed);
        }

        if (previousFocusedElement && typeof previousFocusedElement.focus === "function") {
            previousFocusedElement.focus();
        }
        previousFocusedElement = null;
    }

    function openConfirmDialog(options) {
        var resolvedOptions = options || {};

        if (confirmResolver) {
            resolveConfirmDialog(false);
        }

        confirmDialog.title.textContent = resolvedOptions.title || "Confirmation requise";
        confirmDialog.message.textContent = resolvedOptions.message || "Confirmer cette action ?";
        confirmDialog.confirmButton.textContent = resolvedOptions.confirmLabel || "Confirmer";
        confirmDialog.cancelButton.textContent = resolvedOptions.cancelLabel || "Annuler";
        confirmDialog.dialog.classList.toggle("is-danger", resolvedOptions.tone === "danger");

        previousFocusedElement = document.activeElement;
        confirmDialog.backdrop.hidden = false;
        document.body.classList.add("confirm-dialog-open");

        window.setTimeout(function () {
            confirmDialog.confirmButton.focus();
        }, 0);

        return new Promise(function (resolve) {
            confirmResolver = resolve;
        });
    }

    confirmDialog.cancelButton.addEventListener("click", function () {
        resolveConfirmDialog(false);
    });

    confirmDialog.confirmButton.addEventListener("click", function () {
        resolveConfirmDialog(true);
    });

    confirmDialog.closeButton.addEventListener("click", function () {
        resolveConfirmDialog(false);
    });

    confirmDialog.backdrop.addEventListener("click", function (event) {
        if (event.target === confirmDialog.backdrop) {
            resolveConfirmDialog(false);
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !confirmDialog.backdrop.hidden) {
            event.preventDefault();
            resolveConfirmDialog(false);
        }
    });

    document.querySelectorAll("[data-confirm]").forEach(function (element) {
        element.addEventListener("click", function (event) {
            event.preventDefault();

            openConfirmDialog({
                title: element.getAttribute("data-confirm-title"),
                message: element.getAttribute("data-confirm"),
                confirmLabel: element.getAttribute("data-confirm-accept"),
                cancelLabel: element.getAttribute("data-confirm-cancel"),
                tone: element.getAttribute("data-confirm-tone"),
            }).then(function (confirmed) {
                if (confirmed) {
                    var href = element.getAttribute("href");
                    if (href) {
                        window.location.assign(href);
                    }
                }
            });
        });
    });

    document.querySelectorAll("[data-confirm-form]").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            if (form.dataset.confirmState === "approved") {
                delete form.dataset.confirmState;
                return;
            }

            event.preventDefault();
            var submitter = event.submitter || form.querySelector("[type='submit']");

            openConfirmDialog({
                title: form.getAttribute("data-confirm-title"),
                message: form.getAttribute("data-confirm-form"),
                confirmLabel: form.getAttribute("data-confirm-accept"),
                cancelLabel: form.getAttribute("data-confirm-cancel"),
                tone: form.getAttribute("data-confirm-tone"),
            }).then(function (confirmed) {
                if (confirmed) {
                    form.dataset.confirmState = "approved";
                    if (submitter && typeof form.requestSubmit === "function") {
                        form.requestSubmit(submitter);
                        return;
                    }
                    form.submit();
                }
            });
        });
    });

    if (window.flatpickr) {
        if (window.flatpickr.l10ns && window.flatpickr.l10ns.fr) {
            window.flatpickr.localize(window.flatpickr.l10ns.fr);
        }

        document.querySelectorAll("[data-flatpickr='date']").forEach(function (input) {
            window.flatpickr(input, {
                altInput: true,
                altFormat: "d/m/Y",
                dateFormat: "Y-m-d",
                allowInput: true,
                disableMobile: true,
                locale: "fr",
            });
        });

        document.querySelectorAll("[data-flatpickr='datetime']").forEach(function (input) {
            window.flatpickr(input, {
                altInput: true,
                altFormat: "d/m/Y H:i",
                dateFormat: "Y-m-d\\TH:i",
                enableTime: true,
                time_24hr: true,
                allowInput: true,
                disableMobile: true,
                locale: "fr",
            });
        });
    }

    if (!window.matchMedia || !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        window.requestAnimationFrame(function () {
            document.body.classList.add("app-ready");
        });
    } else {
        document.body.classList.add("app-ready");
    }
});
