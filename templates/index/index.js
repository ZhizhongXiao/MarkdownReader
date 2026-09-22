        (function () {
            function getIndexDirectory() {
                var path = window.location.pathname;
                try {
                    path = decodeURIComponent(path);
                } catch (error) {
                    // A malformed escape sequence must not take the copy feature
                    // down: the raw pathname is a degraded answer, not a crash.
                }
                // A file URL that carries a server host is a network share:
                // file://server/share/x.html is \\server\share\x.html, and the host is
                // the only place where the server name survives.
                // Only a file URL can name a network share here: for any other
                // scheme the host is a web server rather than a UNC server.
                var server = window.location.protocol === "file:" ? window.location.host : "";
                if (server) path = "\\\\" + server + path;
                if (/^\/[A-Za-z]:\//.test(path)) path = path.slice(1);
                path = path.replace(/\//g, "\\");
                return path.slice(0, path.lastIndexOf("\\"));
            }

            function getAbsoluteFolder(relativePath) {
                var base = getIndexDirectory();
                var suffix = relativePath.replace(/\//g, "\\");
                return base + (suffix ? "\\" + suffix : "");
            }

            function fallbackCopy(text) {
                var input = document.createElement("textarea");
                input.value = text;
                input.setAttribute("readonly", "");
                input.style.position = "fixed";
                input.style.opacity = "0";
                document.body.appendChild(input);
                var copied = false;
                try {
                    input.select();
                    // execCommand reports whether the copy happened. Treating a
                    // refusal as success is what made a failed copy look done.
                    copied = document.execCommand("copy") === true;
                } finally {
                    input.remove();
                }
                return copied;
            }

            function copyPath(button, path) {
                var attempt;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    attempt = navigator.clipboard.writeText(path).catch(function () {
                        if (!fallbackCopy(path)) {
                            throw new Error("复制失败");
                        }
                    });
                } else {
                    attempt = fallbackCopy(path)
                        ? Promise.resolve()
                        : Promise.reject(new Error("复制失败"));
                }
                // The success feedback belongs to a copy that really happened,
                // and the rejection is handled here so a failure cannot turn into
                // an unhandled rejection either.
                attempt.then(function () {
                    button.textContent = "✓";
                    button.classList.add("copied");
                    button.title = "已复制";
                    window.setTimeout(function () {
                        button.textContent = "⧉";
                        button.classList.remove("copied");
                        button.title = "复制绝对路径";
                    }, 1200);
                }, function () {
                    // Failure stays failure: the button keeps its normal state.
                });
            }

            document.querySelectorAll(".toggle-btn").forEach(function (button) {
                button.addEventListener("click", function () {
                    var group = button.closest(".folder-group");
                    if (!group) return;
                    var list = group.querySelector(":scope > .document-list");
                    if (!list) return;
                    var expanded = button.getAttribute("aria-expanded") === "true";
                    button.setAttribute("aria-expanded", String(!expanded));
                    button.textContent = expanded ? "▶" : "▼";
                    button.title = expanded ? "展开文件夹" : "折叠文件夹";
                    list.hidden = expanded;
                });
            });

            document.querySelectorAll(".copy-btn").forEach(function (button) {
                button.addEventListener("click", function () {
                    var group = button.closest(".folder-group");
                    if (!group) return;
                    copyPath(button, getAbsoluteFolder(group.dataset.folder || ""));
                });
            });

            var search = document.getElementById("document-search");
            var noResults = document.getElementById("no-results");
            // This page is a generated artifact, so a missing node may only cost its own
            // feature: the block below is skipped, never the whole script.
            if (search) {
                search.addEventListener("input", function () {
                    var query = search.value.trim().toLowerCase();
                    var visibleCount = 0;

                    document.querySelectorAll(".folder-group").forEach(function (group) {
                        var groupCount = 0;
                        group.querySelectorAll(".document-row").forEach(function (row) {
                            var matches = !query || (row.dataset.search || "").includes(query);
                            row.hidden = !matches;
                            if (matches) groupCount += 1;
                        });
                        group.hidden = groupCount === 0;
                        visibleCount += groupCount;
                        if (query && groupCount > 0) {
                            var list = group.querySelector(":scope > .document-list");
                            var toggle = group.querySelector(":scope > .folder-header .toggle-btn");
                            if (list) list.hidden = false;
                            if (toggle) {
                                toggle.textContent = "▼";
                                toggle.setAttribute("aria-expanded", "true");
                            }
                        }
                    });

                    document.querySelectorAll(".root-list .document-row").forEach(function (row) {
                        var matches = !query || (row.dataset.search || "").includes(query);
                        row.hidden = !matches;
                        if (matches) visibleCount += 1;
                    });

                    if (noResults) noResults.hidden = visibleCount !== 0;
                });
            }
        }());
