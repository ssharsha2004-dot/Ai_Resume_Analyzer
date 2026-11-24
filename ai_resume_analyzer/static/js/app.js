document.addEventListener("DOMContentLoaded", () => {
    const input = document.querySelector('input[type="file"]');
    if (input) {
        input.addEventListener("change", () => {
            const file = input.files[0];
            if (file) {
                const box = input.closest(".upload-box");
                const title = box?.querySelector("h5");
                if (title) title.textContent = file.name;
            }
        });
    }
});
