/* Lot assistant: sends the farmer's sentence to /lots/intake and fills the form. Voice uses the browser's Web Speech API
   (works in Chrome/Edge; if unsupported the Speak button is hidden and typing still works). The farmer always confirms. */
(function () {
  var script = document.currentScript, url = script.getAttribute('data-url');
  var txt = document.getElementById('assist_text'), out = document.getElementById('assist_out'),
      st = document.getElementById('assist_status'), form = document.getElementById('lotform'),
      mic = document.getElementById('assist_mic'), lang = document.getElementById('assist_lang');
  if (!txt) return;

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { mic.style.display = 'none'; lang.style.display = 'none'; }
  else {
    mic.addEventListener('click', function () {
      var r = new SR(); r.lang = lang.value; r.interimResults = false;
      st.textContent = 'Listening…';
      r.onresult = function (e) { txt.value = (txt.value + ' ' + e.results[0][0].transcript).trim(); st.textContent = ''; };
      r.onerror = function () { st.textContent = 'Could not hear. Please type instead.'; };
      r.onend = function () { if (st.textContent === 'Listening…') st.textContent = ''; };
      r.start();
    });
  }

  function set(name, value) {
    var el = form.elements[name]; if (!el || value === undefined || value === null) return;
    el.value = value;
  }
  document.getElementById('assist_go').addEventListener('click', function () {
    var fd = new FormData(); fd.append('text', txt.value); fd.append('_csrf', form.elements['_csrf'].value);
    st.textContent = 'Understanding…'; out.textContent = '';
    fetch(url, { method: 'POST', body: fd, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        st.textContent = '';
        if (d.error) { out.textContent = d.error; return; }
        var f = d.fields;
        ['product_form', 'quantity', 'quantity_unit', 'expected_price', 'price_unit', 'location', 'moisture_pct', 'curcumin_pct', 'variety']
          .forEach(function (k) { set(k, f[k]); });
        var qs = (d.questions.mr || []).map(function (q, i) { return '<li>' + q + '<br><span class="muted">' + d.questions.en[i] + '</span></li>'; }).join('');
        out.innerHTML = '<strong>Filled ' + Object.keys(f).length + ' field(s)' + (d.mode === 'llm' ? ' (AI-assisted)' : '') + '.</strong> Please check them.' +
          (qs ? '<br>Still missing — please add:<ul style="margin:.3rem 0 0;padding-left:1.1rem">' + qs + '</ul>' : '<br>Everything needed is filled.');
        form.scrollIntoView({ behavior: 'smooth' });
      })
      .catch(function () { st.textContent = ''; out.textContent = 'Something went wrong. Please fill the form by hand.'; });
  });
})();
