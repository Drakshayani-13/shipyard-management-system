
// Local backend URL
const LOCAL_API = "http://127.0.0.1:5001";

// Replace this with your actual Render backend URL after deployment.
const PRODUCTION_API = "https://ship-portal-api.onrender.com";

const isPortal = location.pathname.startsWith("/portal");
const isLocal = ["localhost", "127.0.0.1"].includes(location.hostname);

window.APP_CONFIG = {
  API_BASE_URL: isPortal
    ? location.origin
    : isLocal
      ? LOCAL_API
      : PRODUCTION_API
};
