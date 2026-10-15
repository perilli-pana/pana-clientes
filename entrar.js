/* ============================================================
   ENTRAR CON GOOGLE — la puerta de Pana
   ------------------------------------------------------------
   Antes había una clave escrita acá mismo (cualquiera que mirara
   el código la veía) y la base se leía sin login. Ahora se entra
   con la cuenta de Google y la base sólo le abre a los mails del
   equipo. La lista NO está acá (este repo es público): vive en las
   reglas de Firebase, en el repo privado ~/marcos/pana/firebase/.
   Para sumar a alguien se agrega su mail ahí y se publica.
   ============================================================ */

/* Carga Firebase (app + login + base) si la página no lo trajo ya. */
function panaCargarFirebase(){
  const libs = ["app", "auth", "database"].map(n => `https://www.gstatic.com/firebasejs/10.12.2/firebase-${n}-compat.js`);
  return libs.reduce((p, src) => p.then(() => {
    if (document.querySelector(`script[src="${src}"]`)) return;
    return new Promise((ok, mal) => { const s = document.createElement("script"); s.src = src; s.onload = ok; s.onerror = mal; document.head.appendChild(s); });
  }), Promise.resolve());
}

/* Muestra la puerta hasta que entre alguien del equipo; después llama a listo(usuario).
   puerta: el elemento que tapa la página. Adentro tiene que haber un botón
   [data-entrar] y un lugar [data-aviso] para los mensajes. */
function panaEntrar(config, puerta, listo){
  panaCargarFirebase().then(() => {
    if (!firebase.apps.length) firebase.initializeApp(config);
    const auth = firebase.auth();
    const aviso = t => { const a = puerta.querySelector("[data-aviso]"); if (a) a.textContent = t; };
    const boton = puerta.querySelector("[data-entrar]");
    let yaEntro = false;
    boton.onclick = () => {
      aviso("");
      const g = new firebase.auth.GoogleAuthProvider();
      g.setCustomParameters({ prompt: "select_account" });
      auth.signInWithPopup(g).catch(e => {
        if (e.code === "auth/popup-blocked" || e.code === "auth/operation-not-supported-in-this-environment") return auth.signInWithRedirect(g);
        if (e.code !== "auth/popup-closed-by-user" && e.code !== "auth/cancelled-popup-request") aviso("No se pudo entrar: " + (e.message || e.code));
      });
    };
    auth.onAuthStateChanged(u => {
      if (!u) { puerta.style.display = ""; boton.hidden = false; return; }
      // la base decide: si este mail no está en las reglas, contesta "permiso denegado"
      firebase.database().ref("panaDashboard/config").once("value").then(() => {
        puerta.style.display = "none";
        if (!yaEntro) { yaEntro = true; listo(u); }
      }).catch(() => {
        aviso(u.email + " no está en el equipo de Pana. Pedile a Marcos que te sume.");
        auth.signOut();
      });
    });
  }).catch(() => {
    const a = puerta.querySelector("[data-aviso]"); if (a) a.textContent = "No se pudo cargar: revisá internet.";
  });
}

function panaSalir(){ firebase.auth().signOut().then(() => location.reload()); }
