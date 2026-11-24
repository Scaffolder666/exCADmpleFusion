/* exCADmple Operation Walkthrough for HiM — browser-side presentation.
 *
 * A timeline step can be accompanied by real footage of HOW to use the CAD
 * tool. The film is an optional clip; the reference model/HiM is still the
 * live 3D source of truth, and the learner's active Fusion tool is untouched.
 *
 * Each step has authored walkthrough moments or falls back to a clearly
 * marked reconstruction based on its FEATURE KIND. Generated descriptions
 * must never be presented as original designer mouse/keyboard history.
 */
"use strict";
window.OperationWalkthrough = (() => {
  const $ = id => document.getElementById(id);
  const phaseLabels = {tool:"Tool", how:"How", geometry:"Geometry", why:"Why"};
  let handlers = null, currentVideo = "", currentStep = -1, selectedMoment = -1;
  let lastVisualKey = "", lastSeek = -Infinity, movieAudioEnabled = true;
  const video = () => $("walkVideo");

  function text(value) { return String(value === undefined || value === null ? "" : value); }
  function escapeMoment(m) {
    return {
      at_ms: Number(m.at_ms) || 0,
      kind: ["tool","how","geometry","why"].includes(m.kind) ? m.kind : "how",
      title: text(m.title),
      description: text(m.description),
      video_start_ms: Number.isFinite(m.video_start_ms) ? m.video_start_ms : null,
      video_end_ms: Number.isFinite(m.video_end_ms) ? m.video_end_ms : null,
      video_focus: m.video_focus || null,
    };
  }
  function operationName(step) {
    const f = (step.source_features || []).at(-1) || {};
    return text(f.kind || (step.tools || []).at(-1) || "").toLowerCase();
  }
  function howFor(step) {
    const kind = operationName(step);
    if (/sketch|line|rectangle|spline/.test(kind))
      return "Sketch the reference profile; inspect the source geometry and constraints. The original point-by-point clicks are not stored in .f3d.";
    if (/extrud/.test(kind))
      return "Select the source profile, choose an operation, set the direction and extrusion distance, then confirm.";
    if (/fillet|chamfer/.test(kind))
      return "Select the target edges, adjust the radius or distance, inspect the preview, then confirm.";
    if (/revolv/.test(kind))
      return "Select a profile and revolution axis, enter the angle, inspect the result, then confirm.";
    if (/pattern/.test(kind))
      return "Select the bodies or features, set a direction, quantity and spacing, then confirm.";
    if (/hole/.test(kind))
      return "Choose the hole location, select type/depth/diameter and confirm.";
    if (/mov|rotat/.test(kind))
      return "Select the object, choose the manipulator and apply the desired transform.";
    return "Inspect the feature's inputs and parameters, then apply the same command to your own design.";
  }
  function plainReason(step) {
    // Synthetic hypotheses generated from a Timeline are NEVER original
    // designer reasoning. Do not show them as a "Why" walkthrough moment.
    if (["simulated", "hypothetical"].includes(step.reasoning_source)) return "";
    const cues = step.cues || [];
    return cues.length ? text(cues[0].label) : "";
  }
  function derivedMoments(step, toolInfo) {
    const duration = Math.max(500, Number(step.duration_ms) || 8000);
    const tool = ((toolInfo && toolInfo.tools) || []).find(t=>t.found) ||
                 ((toolInfo && toolInfo.tools) || [])[0];
    const toolName = tool ? text(tool.label) : text((step.tools || [])[0] || "CAD tool");
    const where = tool && tool.found ? tool.path.join(" › ") : toolName;
    const params = (step.parameters || []).slice(0, 4).map(p =>
      [p.name || p.label, p.expression || p.value].filter(Boolean).join(": ")).filter(Boolean);
    const out = [
      {at_ms:0, kind:"tool",title:"Find and choose " + toolName,
       description:where + " · The current Fusion tool is also pinned in the exCADmple toolbar."},
      {at_ms:duration * .23,kind:"how",title:"Watch the actual operation",
       description:howFor(step)},
      {at_ms:duration * .62,kind:"geometry",title:"Inspect the affected geometry",
       description:(params.length ? "Parameters: " + params.join(" · ") + ". " : "") +
          "The reference geometry is highlighted by HiM; your own model remains editable."}
    ];
    const reason = plainReason(step);
    if (reason) out.push({at_ms:duration * .83,kind:"why",title:"Author's explanation",description:reason});
    return out.map(escapeMoment);
  }
  function moments(step, tools) {
    const explicit = step.walkthrough;
    if (Array.isArray(explicit) && explicit.length)
      return explicit.map(escapeMoment).sort((a,b)=>a.at_ms-b.at_ms);
    return derivedMoments(step,tools);
  }
  function momentAt(moments, elapsed) {
    let index = 0;
    moments.forEach((m,i)=>{if (elapsed >= m.at_ms) index=i;});
    return index;
  }
  function textNode(name, attrs, content) {
    const e=document.createElement(name);
    for(const [k,v] of Object.entries(attrs||{})) e.setAttribute(k,v);
    if(content!==undefined) e.textContent=text(content);
    return e;
  }
  function setVideoSource(item) {
    const resource = item && item.media && item.media.video;
    const src = resource || "";
    if (src===currentVideo) return;
    const v=video();
    v.pause();
    v.removeAttribute("src");
    v.load();
    currentVideo=src;
    lastSeek=-Infinity;
    if(src) { v.src=src; v.load(); }
    $("walkVideoWrap").hidden=!src;
    $("walkNoVideo").hidden=!!src;
  }
  function videoWindow(moment,item) {
    const focus = moment.video_focus || (item.media && item.media.video_focus) || {};
    const x = Number(focus.x), y=Number(focus.y), zoom=Number(focus.scale);
    const cx=Number.isFinite(x) && x>=0 && x<=1 ? x : .5;
    const cy=Number.isFinite(y) && y>=0 && y<=1 ? y : .5;
    const z=Number.isFinite(zoom) && zoom>=1 && zoom<=4 ? zoom : 1;
    const v=video();
    v.style.transformOrigin=(cx*100)+"% "+(cy*100)+"%";
    v.style.transform="scale("+z+")";
  }
  function syncVideo(item,moment,next,elapsed,playing,rate) {
    if(!(item.media && item.media.video) || !moment) return;
    const v=video();
    // A separate author narration track has priority; otherwise the actual
    // recording may carry the author speaking during the operation.
    v.muted=!!(item.media && item.media.audio) || !movieAudioEnabled;
    $("walkSound").textContent=v.muted?"Sound off":"Sound on";
    $("walkSound").disabled=!!(item.media && item.media.audio);
    videoWindow(moment,item);
    const offset=Number(item.media.video_offset_ms)||0;
    const start=moment.video_start_ms===null ? Math.max(0,moment.at_ms) : moment.video_start_ms;
    const end=moment.video_end_ms===null ? Math.max(start,next || Number(item.duration_ms)||8000) : moment.video_end_ms;
    const local=Math.max(0,elapsed-moment.at_ms);
    const desired=(offset+Math.max(start,Math.min(end,start+local)))/1000;
    if(v.readyState > 0 && (Math.abs(v.currentTime-desired)>.32 || lastSeek===-Infinity)) {
      try { v.currentTime=desired; lastSeek=desired; } catch(_) {}
    }
    v.playbackRate=Math.max(.5,Math.min(2,Number(rate)||1));
    if(playing && elapsed>=moment.at_ms && desired<(offset+end)/1000-.06) {
      if(v.paused) v.play().catch(()=>{});
    } else if(!v.paused) v.pause();
  }
  function reset() {
    currentStep=-1;selectedMoment=-1;lastVisualKey="";
    const v=video();
    if(v) {v.pause();currentVideo="";v.removeAttribute("src");v.load();}
    $("walkthrough").hidden=true;
  }
  function sync({item,index,elapsed,playing,tools,rate}) {
    if(!item) {reset();return;}
    const list=moments(item,tools);
    if(!list.length) return;
    const active=momentAt(list,elapsed);
    if(index!==currentStep) {
      currentStep=index;selectedMoment=-1;lastVisualKey="";
      setVideoSource(item);
    }
    const visualKey=JSON.stringify([index,active,tools && tools.index===index ? tools : null,list]);
    const chosen=list[active];
    $("walkthrough").hidden=false;
    if(visualKey!==lastVisualKey) {
      lastVisualKey=visualKey;
      $("walkKind").textContent=phaseLabels[chosen.kind]||"How";
      $("walkTitle").textContent=chosen.title;
      $("walkDescription").textContent=chosen.description;
      $("walkOrigin").textContent=Array.isArray(item.walkthrough) && item.walkthrough.length
        ? "Authored walkthrough" : "Reconstructed guidance · not original mouse history";
      if (chosen.kind==="why") $("walkOrigin").textContent +=
        item.reasoning_source==="simulated" ? " · unverified rationale" : " · supplied narration";
      const track=$("walkMoments");
      track.replaceChildren();
      list.forEach((m,i)=>{
        const b=textNode("button",{
          type:"button",class:"walk-moment"+(i===active?" active":""),
          title:m.title, "aria-label":"Jump to " + m.title
        },(i+1)+" "+(phaseLabels[m.kind]||"How"));
        b.addEventListener("click",()=>handlers && handlers.seek(m.at_ms));
        track.appendChild(b);
      });
      const tool=(tools && tools.index===index && tools.tools || []).find(t=>t.found) ||
                 (tools && tools.index===index && tools.tools || [])[0];
      const toolTarget=$("walkTool");
      const toolName=tool?text(tool.label):text((item.tools||[])[0]||"Tool");
      toolTarget.textContent=toolName;
      toolTarget.classList.toggle("spotlight",chosen.kind==="tool");
      $("walkToolPath").textContent=tool&&tool.found?tool.path.join(" › "):"Locate this command in Fusion";
      $("walkTry").disabled=!(tool && tool.found);
      $("walkTry").onclick=()=>{
        if(!tool||!tool.found||!handlers) return;
        handlers.useTool(tool.label);
      };
      $("walkVideoNote").textContent= item.media && item.media.video
        ? "Actual screen recording · synced clip" : "No screen recording for this step. The 3D HiM view still shows its inputs/result.";
      $("walkFocus").textContent=chosen.kind==="geometry"?
        "3D input / output highlighted in the reference model":"Reference geometry visible in the same viewport";
    }
    syncVideo(item,chosen,active+1<list.length?list[active+1].at_ms:Number(item.duration_ms)||8000,
              elapsed,playing,rate);
  }
  function init(callbacks) {
    handlers=callbacks;
    $("walkPrevious").addEventListener("click",()=>{
      const item=handlers.getItem();
      if(!item) return;
      const list=moments(item,handlers.getTools());
      const index=momentAt(list,handlers.getElapsed());
      handlers.seek(list[Math.max(0,index-1)].at_ms);
    });
    $("walkNext").addEventListener("click",()=>{
      const item=handlers.getItem();
      if(!item) return;
      const list=moments(item,handlers.getTools());
      const index=momentAt(list,handlers.getElapsed());
      handlers.seek(list[Math.min(index+1,list.length-1)].at_ms);
    });
    $("walkReplay").addEventListener("click",()=>{
      const item=handlers.getItem();
      if(!item) return;
      const list=moments(item,handlers.getTools());
      handlers.seek(list[momentAt(list,handlers.getElapsed())].at_ms);
    });
    $("walkSound").addEventListener("click",()=>{movieAudioEnabled=!movieAudioEnabled; video().muted=!movieAudioEnabled; $("walkSound").textContent=movieAudioEnabled?"Sound on":"Sound off";});
    video().addEventListener("click",()=>handlers.togglePause());
  }
  return {init,sync,reset,moments,momentAt};
})();
