import '@testing-library/jest-dom/vitest'

/**
 * The console renders an SVG chart and reads `matchMedia` indirectly through
 * CSS only, so no polyfills are needed beyond a clean document between tests.
 */
afterEach(() => {
  document.body.innerHTML = ''
})
