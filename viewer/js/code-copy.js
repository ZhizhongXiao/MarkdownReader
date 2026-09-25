    // ═══════════════════════════════════════════════════════════════
    // Module 6: Code Copy
    // ═══════════════════════════════════════════════════════════════
    function initCodeCopy() {
        markdownBody.querySelectorAll("pre").forEach(function (pre) {
            if (pre.parentElement.classList.contains("code-block-wrapper")) return;
            var wrapper = document.createElement("div");
            wrapper.className = "code-block-wrapper";
            pre.parentNode.insertBefore(wrapper, pre);
            wrapper.appendChild(pre);
            var copyBtn = document.createElement("button");
            copyBtn.className = "copy-btn"; copyBtn.textContent = "复制";
            copyBtn.addEventListener("click", function (e) {
                e.preventDefault(); e.stopPropagation();
                var code = pre.textContent || "";
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(code).then(function () { copyBtn.textContent = "已复制"; setTimeout(function () { copyBtn.textContent = "复制"; }, 1500); })
                        .catch(function () { fallbackCopy(code, copyBtn); });
                } else { fallbackCopy(code, copyBtn); }
            });
            wrapper.appendChild(copyBtn);
        });
        function fallbackCopy(text, btn) {
            var textarea = document.createElement("textarea");
            textarea.value = text; textarea.style.position = "fixed"; textarea.style.left = "-9999px";
            document.body.appendChild(textarea); textarea.select();
            try { document.execCommand("copy"); btn.textContent = "已复制"; }
            catch (err) { btn.textContent = "失败"; }
            setTimeout(function () { btn.textContent = "复制"; }, 1500);
            document.body.removeChild(textarea);
        }
    }

