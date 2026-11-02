/* Physical coordinates only. No matching of part extents or automatic rescaling. */
(() => {
  'use strict';
  const finite = values => values.every(Number.isFinite);
  function checkedPitch(values) {
    if (!finite(values) || Math.min(...values) < 1e-9 || Math.max(...values) > 1e6) throw Error('Масштаб вне допустимого диапазона: от 10⁻⁹ до 10⁶ мм/px.');
    return values;
  }
  function drawingPitch(metadata, ratio) {
    const match = String(ratio).trim().match(/^([0-9]+(?:[.,][0-9]+)?)\s*:\s*([0-9]+(?:[.,][0-9]+)?)$/);
    const dpi = metadata?.dpi;
    if (!match || !Array.isArray(dpi) || dpi.length !== 2) throw Error('Нужны DPI листа и масштаб чертежа, например 1:1 или 1:2.');
    const [numerator, denominator] = match.slice(1).map(v => Number(v.replace(',', '.')));
    if (!finite([...dpi, numerator, denominator]) || Math.min(...dpi, numerator, denominator) <= 0) throw Error('Некорректный масштаб.');
    // At 1:2 a 10 mm line on paper represents 20 mm of the part.
    return checkedPitch(dpi.map(v => 25.4 / v * denominator / numerator));
  }
  function calibratedPitch(a, b, length) {
    const distance = Math.hypot(b.x - a.x, b.y - a.y);
    if (!finite([a.x, a.y, b.x, b.y, length, distance]) || length <= 0 || distance < 2) throw Error('Укажите две разные точки (не ближе 2 px) и положительный размер в мм.');
    return checkedPitch([length / distance, length / distance]);
  }
  const resetPose = () => ({x: 0, y: 0, angle: 0, pivot: {x: 0, y: 0}});
  function world(point, pitch, pose = resetPose()) {
    const angle = pose.angle * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
    const x = (point.x - pose.pivot.x) * pitch[0], y = (point.y - pose.pivot.y) * pitch[1];
    return {x: pose.x + c * x - s * y, y: pose.y + s * x + c * y};
  }
  function source(point, pitch, pose = resetPose()) {
    const angle = pose.angle * Math.PI / 180, c = Math.cos(angle), s = Math.sin(angle);
    const x = point.x - pose.x, y = point.y - pose.y;
    return {x: (c * x + s * y) / pitch[0] + pose.pivot.x, y: (-s * x + c * y) / pitch[1] + pose.pivot.y};
  }
  function align(a, b, pitchA, pose) {
    const target = world(a, pitchA);
    return {...pose, x: target.x, y: target.y, pivot: {...b}};
  }
  function comparable(kinds, confirmed) {
    if (kinds.every(k => k === 'drawing')) return true;
    return kinds.every(k => k === 'model') && confirmed === true;
  }
  const api = {drawingPitch, calibratedPitch, resetPose, world, source, align, comparable};
  globalThis.ArchivariusTraceGeometry = api;
  if (typeof module !== 'undefined') module.exports = api;
})();
