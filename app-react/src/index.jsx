/**
 * index.jsx — Entry point, den allra första JS-filen som körs.
 * Kopplar ihop React med HTML:en (index.html → <div id="root">).
 *
 * BEROENDEN:
 *   index.html         → <div id="root"> (där React monteras)
 *   ./index.css         → grundstilar (body, font)
 *   ./App.jsx           → huvudkomponenten som renderas
 *   ./reportWebVitals   → prestanda-mätning (oanvänd utan callback)
 *
 * BEHÖVER INTE RÖRAS — alla ändringar sker i App.jsx och server.py.
 */
import { StrictMode } from "react"; // StrictMode: extra varningar under utveckling (dubbla renderingar för att hitta buggar)
import ReactDOM from "react-dom/client"; // ReactDOM: Reacts koppling till webbläsarens DOM
import "./index.css"; // Grundstilar: body, font-family etc.
import App from "./App"; // Huvudkomponenten med all app-logik
import reportWebVitals from "./reportWebVitals"; // Prestandamätning (gör inget utan callback)

// Hitta <div id="root"> i index.html och skapa en React-rot där
const root = ReactDOM.createRoot(document.getElementById("root"));
// Rendera App-komponenten inuti roten, omsluten av StrictMode
root.render(
  <StrictMode>
    <App />
  </StrictMode>,
);

// If you want to start measuring performance in your app, pass a function
// to log results (for example: reportWebVitals(console.log))
// or send to an analytics endpoint. Learn more: https://bit.ly/CRA-vitals
reportWebVitals();
