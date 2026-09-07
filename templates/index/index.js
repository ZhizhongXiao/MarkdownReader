        (function () {
            function getIndexDirectory() {
                var path = decodeURIComponent(window.location.pathname);
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
                input.select();
                document.execCommand("copy");
                input.remove();
            }

            function copyPath(button, path) {
                var operation;
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    operation = navigator.clipboard.writeText(path).catch(function () {
                        fallbackCopy(path);
                    });
                } else {
                    fallbackCopy(path);
                    operation = Promise.resolve();
                }
                operation.then(function () {
                    button.textContent = "✓";
                    button.classList.add("copied");
                    button.title = "已复制";
                    window.setTimeout(function () {
                        button.textContent = "⧉";
                        button.classList.remove("copied");
                        button.title = "复制绝对路径";
                    }, 1200);
                });
            }

            document.querySelectorAll(".toggle-btn").forEach(function (button) {
                button.addEventListener("click", function () {
                    var group = button.closest(".folder-group");
                    var list = group.querySelector(":scope > .document-list");
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
                    copyPath(button, getAbsoluteFolder(group.dataset.folder || ""));
                });
            });

            var search = document.getElementById("document-search");
            var noResults = document.getElementById("no-results");
            search.addEventListener("input", function () {
                var query = search.value.trim().toLocaleLowerCase();
                var visibleCount = 0;

                document.querySelectorAll(".folder-group").forEach(function (group) {
                    var groupCount = 0;
                    group.querySelectorAll(".document-row").forEach(function (row) {
                        var matches = !query || row.dataset.search.includes(query);
                        row.hidden = !matches;
                        if (matches) groupCount += 1;
                    });
                    group.hidden = groupCount === 0;
                    visibleCount += groupCount;
                    if (query && groupCount > 0) {
                        var list = group.querySelector(":scope > .document-list");
                        var toggle = group.querySelector(":scope > .folder-header .toggle-btn");
                        list.hidden = false;
                        toggle.textContent = "▼";
                        toggle.setAttribute("aria-expanded", "true");
                    }
                });

                document.querySelectorAll(".root-list .document-row").forEach(function (row) {
                    var matches = !query || row.dataset.search.includes(query);
                    row.hidden = !matches;
                    if (matches) visibleCount += 1;
                });

                noResults.hidden = visibleCount !== 0;
            });
        }());
