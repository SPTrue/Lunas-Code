'use strict';
const $ = id => document.getElementById(id);
const native = typeof window.Luna !== 'undefined';
const ALL = (1 << 13) - 1;
const steps = [
  ['Left eye · horizontal center', 'Center the left eye horizontally.'],
  ['Left eye · vertical center', 'Center the left eye vertically.'],
  ['Right eye · horizontal center', 'Center the right eye horizontally.'],
  ['Right eye · vertical center', 'Center the right eye vertically.'],
  ['Left eyelid · open', 'Set the relaxed, open eyelid position.'],
  ['Left eyelid · closed', 'Close the eyelid gently. Do not force it against a stop.'],
  ['Right eyelid · open', 'Set the relaxed, open eyelid position.'],
  ['Right eyelid · closed', 'Close the eyelid gently. Do not force it against a stop.'],
  ['Jaw · closed', 'Set the relaxed, closed mouth position.'],
  ['Jaw · open', 'Set the maximum safe mouth opening.'],
  ['Neck · horizontal center', 'Support the head and center it left-to-right.'],
  ['Neck · vertical center', 'Support the head and set its resting tilt.'],
  ['Tail · center', 'Set the resting tail position. Saving the final outstanding step enables idle motion.']
];
let connected = false, owner = 0, confirmed = 0, cal = 255, selected = 0;
let saving = false, dryRun = false, micPresent = false;
let values = [0, 0, 0, 0, 0, 0, 0];
let page = 'panel', lastInput = '';
const errors = ['', 'Invalid command.', 'Take control first.', 'Complete all calibration steps first.',
  'Finish or discard the current calibration adjustment.', 'No microphone detected.',
  'Another phone currently has control.'];
function send(opcode, ...payload) {
  if (native && connected) window.Luna.send(JSON.stringify([1, opcode, ...payload]));
}
function inputs(force = false) {
  if (owner !== 1 || confirmed !== ALL || cal !== 255) return;
  const next = values.join(',');
  if (force || next !== lastInput) { send(4, ...values); lastInput = next; }
}
function resetControls() {
  values = [0, 0, 0, 0, 0, 0, 0];
  $('jaw').value = $('lids').value = '0';
  document.querySelectorAll('.knob').forEach(knob => { knob.style.transform = ''; });
  lastInput = '';
  inputs(true);
}
function show(target) {
  if (page === 'panel') resetControls();
  page = target;
  ['panel', 'connection-panel', 'settings-panel', 'calibration-panel']
    .forEach(id => { $(id).hidden = id !== target; });
  window.scrollTo(0, 0);
}
function render() {
  const owns = connected && owner === 1;
  $('motion').disabled = !owns || confirmed !== ALL || cal !== 255;
  for (const id of ['head-stick', 'eyes-stick']) {
    $(id).setAttribute('aria-disabled', String($('motion').disabled));
    $(id).tabIndex = $('motion').disabled ? -1 : 0;
  }
  $('take').disabled = !connected || owns;
  $('release').disabled = !owns;
  $('mic').disabled = !owns || !micPresent || cal !== 255;
  $('idle').disabled = !owns || cal !== 255;
  $('story-start').disabled = $('story-stop').disabled = !owns || confirmed !== ALL || cal !== 255;
  $('mode').textContent = dryRun ? 'DRY RUN · NO MOTORS' : !connected ? 'OFFLINE' :
    cal !== 255 ? 'CALIBRATING' : confirmed !== ALL ? 'SETUP REQUIRED' :
    owner === 1 ? 'PHONE CONTROL' : owner === 2 ? 'PS4 CONTROL' : 'NEUTRAL / IDLE';
  $('hint').textContent = !connected ? 'Connect to Luna to begin.' : !owns ?
    'Take control to use the panel.' : confirmed !== ALL ? 'Open Settings → Joint calibration.' :
    'Release controls to return to rest.';
  $('mic-detail').textContent = !connected ? 'Pi microphone · waiting for connection' :
    micPresent ? 'Pi microphone · manual jaw takes priority' : 'Microphone not detected';
  $('dot').classList.toggle('online', connected);
  $('connect').textContent = connected ? 'Disconnect' : 'Connect';
  $('cal-begin').disabled = !owns || cal !== 255;
  for (const id of ['minus', 'plus', 'cal-save', 'cal-cancel']) $(id).disabled = !owns || cal === 255 || saving;
  $('step-select').disabled = cal !== 255 || saving;
  $('cal-progress').textContent = `${confirmed.toString(2).split('1').length - 1} of 13 positions saved. ` +
    (confirmed === ALL ? 'Calibration complete. Normal idle movement is enabled.' : 'Normal movement stays locked until all are saved.');
  $('step-count').textContent = `STEP ${selected + 1} / 13${confirmed & (1 << selected) ? ' · SAVED' : ''}`;
  $('step-label').textContent = steps[selected][0];
  $('step-instruction').textContent = steps[selected][1];
  $('step-select').value = String(selected);
  $('cal-begin').hidden = cal !== 255;
}
window.nativeEvent = function(type, data) {
  if (type === 'connection') $('connection').textContent = data;
  if (type === 'error') $('error').textContent = data;
  if (type === 'connected') {
    connected = data;
    $('error').textContent = '';
    if (!data) {
      owner = 0; cal = 255; saving = false; dryRun = false; confirmed = 0;
      resetControls();
      $('connection').textContent = 'Not connected';
    }
    render();
  }
  if (type === 'devices') {
    $('devices').replaceChildren();
    data.forEach(device => {
      const row = document.createElement('div'); row.className = 'device';
      const text = document.createElement('span'); text.textContent = device.name;
      const address = document.createElement('small'); address.textContent = device.address; text.append(address);
      const button = document.createElement('button'); button.textContent = 'Pair / connect';
      button.addEventListener('click', () => { if (native) window.Luna.connect(device.address); });
      row.append(text, button); $('devices').append(row);
    });
  }
  if (type === 'status') {
    if (data.length !== 13 || data[0] !== 1) {
      $('error').textContent = 'Incompatible Pi protocol. Update both app and service.';
      if (native) window.Luna.disconnect();
      return;
    }
    const previousOwner = owner;
    owner = data[1]; micPresent = !!data[2];
    $('mic').checked = !!data[3]; $('idle').checked = !!data[4];
    cal = data[5]; confirmed = data[10] | (data[11] << 8); dryRun = !!(data[12] & 2);
    const raw = data[6] | (data[7] << 8);
    $('cal-angle').textContent = cal === 255 ? '—' : `${(raw > 32767 ? raw - 65536 : raw) / 10}°`;
    $('error').textContent = errors[data[8]] || '';
    $('story-state').textContent = data[12] & 1 ? 'Story jaw track is playing' : 'Stopped';
    if (previousOwner !== owner) resetControls();
    if (cal !== 255) selected = cal;
    if (saving && cal === 255) {
      saving = false;
      if (confirmed & (1 << selected)) selected = Math.min(selected + 1, steps.length - 1);
    }
    if (connected && owner === 1 && page === 'connection-panel') show('panel');
    render();
  }
};
$('connect').onclick = () => { if (connected && native) window.Luna.disconnect(); else show('connection-panel'); };
$('scan').onclick = () => {
  if (native) window.Luna.scan();
  else $('error').textContent = 'Layout preview only. Install the Android APK to use Bluetooth.';
};
$('settings').onclick = () => {
  if (cal !== 255) return;
  show(page === 'settings-panel' ? 'panel' : 'settings-panel');
};
document.querySelectorAll('.back').forEach(button => { button.onclick = () => show('panel'); });
$('take').onclick = () => { resetControls(); send(2); };
$('release').onclick = () => { resetControls(); send(3); };
$('mic').onchange = event => send(5, Number(event.target.checked));
$('idle').onchange = event => send(6, Number(event.target.checked));
$('story-start').onclick = () => send(11, 1);
$('story-stop').onclick = () => send(11, 0);
$('calibration-link').onclick = () => { resetControls(); show('calibration-panel'); render(); };
steps.forEach((step, index) => {
  const option = document.createElement('option'); option.value = index; option.textContent = `${index + 1}. ${step[0]}`;
  $('step-select').append(option);
});
$('step-select').onchange = event => { selected = Number(event.target.value); render(); };
$('cal-begin').onclick = () => send(7, selected);
$('minus').onclick = () => send(8, -1);
$('plus').onclick = () => send(8, 1);
$('cal-save').onclick = () => { saving = true; send(9); render(); };
$('cal-cancel').onclick = () => send(10);
$('cal-exit').onclick = () => { send(10); saving = false; show('settings-panel'); };

function stick(id, index) {
  const pad = $(id), knob = pad.querySelector('.knob');
  let activePointer = null;
  const allowed = () => !$('motion').disabled;
  function update(x, y) {
    if (!allowed()) return;
    const length = Math.hypot(x, y);
    if (length > 1) { x /= length; y /= length; }
    values[index] = Math.round(x * 100); values[index + 1] = Math.round(y * 100);
    const radius = (pad.clientWidth - knob.clientWidth) / 2 - 8;
    knob.style.transform = `translate(${x * radius}px,${y * radius}px)`;
    inputs();
  }
  function position(event) {
    const rect = pad.getBoundingClientRect();
    const radius = (pad.clientWidth - knob.clientWidth) / 2 - 8;
    update((event.clientX - rect.left - rect.width / 2) / radius,
      (event.clientY - rect.top - rect.height / 2) / radius);
  }
  pad.onpointerdown = event => {
    if (!allowed() || activePointer !== null) return;
    activePointer = event.pointerId; pad.setPointerCapture(event.pointerId); position(event);
  };
  pad.onpointermove = event => { if (event.pointerId === activePointer) position(event); };
  function end(event) {
    if (event.pointerId !== activePointer) return;
    activePointer = null;
    values[index] = values[index + 1] = 0; knob.style.transform = ''; inputs(true);
  }
  pad.onpointerup = pad.onpointercancel = pad.onlostpointercapture = end;
  pad.onkeydown = event => {
    const direction = {ArrowLeft: [-.5, 0], ArrowRight: [.5, 0], ArrowUp: [0, -.5], ArrowDown: [0, .5]}[event.key];
    if (direction) { event.preventDefault(); update(...direction); }
  };
  pad.onkeyup = event => {
    if (event.key.startsWith('Arrow')) { values[index] = values[index + 1] = 0; knob.style.transform = ''; inputs(true); }
  };
}
stick('head-stick', 0); stick('eyes-stick', 2);
for (const [id, index] of [['jaw', 4], ['lids', 5]]) {
  const range = $(id);
  range.oninput = () => { values[index] = Number(range.value); inputs(); };
  const release = () => { range.value = '0'; values[index] = 0; inputs(true); };
  range.onpointerup = range.onpointercancel = range.onlostpointercapture = range.onblur = release;
  range.onkeyup = release;
}
const wide = $('wide');
wide.onpointerdown = event => {
  if ($('motion').disabled) return;
  wide.setPointerCapture(event.pointerId); values[6] = 1; inputs(true);
};
wide.onpointerup = wide.onpointercancel = wide.onlostpointercapture = wide.onblur = () => { values[6] = 0; inputs(true); };
wide.onkeydown = event => { if (event.code === 'Space' || event.code === 'Enter') { values[6] = 1; inputs(); } };
wide.onkeyup = () => { values[6] = 0; inputs(true); };
window.addEventListener('blur', resetControls);
document.addEventListener('visibilitychange', () => {
  if (document.hidden) { resetControls(); send(3); }
});
setInterval(() => { if (connected && !document.hidden) send(1); }, 250);
if (!native) $('preview-note').hidden = false;
render();
