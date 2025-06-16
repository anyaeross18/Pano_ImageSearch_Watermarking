// Wait for the DOM to be fully loaded
document.addEventListener("DOMContentLoaded", function () {
    const heroContent = document.querySelector('.hero-content');
    if (heroContent) {
        heroContent.classList.add('visible');
    }

    // Add any other JS for your site here
});