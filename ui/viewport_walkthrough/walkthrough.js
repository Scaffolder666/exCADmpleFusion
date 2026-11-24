"use strict";
/* This page is displayed INSIDE the real Fusion 3D viewport by a floating
   Palette. It never creates a second CAD canvas and never sends a command
   to the learner's design. All playback controls stay in the right panel. */
(() => {
  const $ = id => document.getElementById(id);
  const s = {key:"",src:"",lastSeek:-1,pending:null,playing:false,focusLocked:false};
  const v = $("video");
  function clamp(n,a,b) { return Math.min(b,Math.max(a,n)); }
  function setMedia(uri) {
    if(s.src===uri) return;
    v.pause();
    v.removeAttribute("src");
    s.src=uri||"";
    s.lastSeek=-1;
    if(s.src) v.src=s.src;
    v.load();
  }
  function validFocus(focus) {
    const x=Number(focus && focus.x),y=Number(focus && focus.y),z=Number(focus && focus.scale);
    return {
      x:Number.isFinite(x)?clamp(x,0,1):.5,
      y:Number.isFinite(y)?clamp(y,0,1):.5,
      scale:Number.isFinite(z)?clamp(z,1,4):1
    };
  }
  function show(frame) {
    if(!frame || frame.visible===false) {
      s.key="";
      v.pause(); v.removeAttribute("src"); s.src="";v.load();
      $("content").hidden=true; $("empty").hidden=false;
      return;
    }
    $("content").hidden=false; $("empty").hidden=true;
    const phase=String(frame.phase || "tool");
    // Authored cuts can show REAL toolbar clicks during Tool, drawing
    // during How, and numeric confirmation during Geometry as needed.
    const isVideo=!!frame.show_video && !!frame.video;
    const key=[frame.step_id,frame.moment,phase,frame.tool,frame.video].join(":");
    if(key!==s.key) {
      s.key=key;
      $("phase").textContent=phase.toUpperCase();
      $("title").textContent=frame.title||"CAD operation";
      $("hint").textContent=frame.hint||"";
      $("toolName").textContent=frame.tool||"CAD tool";
      const path=frame.tool_path||[];
      $("toolPath").textContent=path.length?path.join(" › "):"Native Fusion tool";
      $("toolFocus").classList.toggle("active",phase==="tool");
      $("tryTool").hidden=phase!=="tool"||!frame.tool_found;
      $("tryTool").dataset.tool=frame.tool||"";
      const glyph=$("toolGlyph");glyph.replaceChildren();
      // From native Fusion's CommandDefinition icon. Never scrape UI images.
      if(frame.tool_icon && /^file:|^data:image\//.test(frame.tool_icon)){
        const img=document.createElement("img");img.src=frame.tool_icon;img.alt="";
        img.onerror=()=>{glyph.textContent="⌘";};glyph.appendChild(img);
      } else glyph.textContent="⌘";
      $("videoShell").hidden=!isVideo;
      $("geometryMark").hidden=phase!=="geometry";
      $("reason").hidden=phase!=="why"||!frame.reason;
      $("reasonText").textContent=frame.reason||"";
      const params=$("parameters");params.replaceChildren();
      for(const p of (frame.parameters||[]).slice(0,4)){
        const span=document.createElement("span");span.textContent=p;params.appendChild(span);
      }
      params.hidden=!(phase==="how"||phase==="geometry")||params.childElementCount===0;
      $("origin").textContent=isVideo?"Original CAD recording":
        (frame.source==="authored"?"Authored operation":"Reconstructed guidance · source CAD geometry");
      $("stepCount").textContent=(Number(frame.index)+1)+" · "+(Number(frame.moment)+1)+"/"+frame.count;
    }
    $("progress").firstElementChild.style.width =
      (100*clamp(Number(frame.elapsed_ms)/Math.max(1,Number(frame.duration_ms)),0,1))+"%";
    // The operation film must show only the corresponding author's actions;
    // one long source video is cut by timestamps without destructive exports.
    if(isVideo) {
      setMedia(frame.video);
      const f=validFocus(frame.video_focus);
      v.style.transformOrigin=(f.x*100)+"% "+(f.y*100)+"%";
      v.style.transform="scale("+f.scale+")";
      const start=Number(frame.video_start_ms)||0, end=Number(frame.video_end_ms)||0;
      const base=Number(frame.video_offset_ms)||0;
      const local=clamp(Number(frame.elapsed_ms)-Number(frame.moment_start_ms),0,Math.max(0,end-start));
      const target=(base+start+local)/1000;
      if(v.readyState>=1 && (s.lastSeek<0||Math.abs(v.currentTime-target)>.38)) {
        try{v.currentTime=target;s.lastSeek=target;}catch(_) {}
      }
      v.playbackRate=clamp(Number(frame.rate)||1,.5,2);
      // The original audio/narration remains in the right player. Muted film
      // avoids two overlapping spoken tracks. A later authoring switch can
      // designate the video as sole audio if desired.
      v.muted=!!frame.has_narration_audio;
      if(frame.playing && local<end-start-.08) {
        if(v.paused) v.play().catch(()=>{});
      } else if(!v.paused) v.pause();
    } else if(!v.paused) v.pause();
    s.playing=!!frame.playing;
  }
  // Only an explicit learner click may start a real CAD command.
  $("tryTool").addEventListener("click",()=>{
    const label=$("tryTool").dataset.tool;
    if(!label) return;
    try {window.adsk.fusionSendData("try_tool",JSON.stringify({label}));}catch(_){}
  });
  v.addEventListener("error",()=>{
    if(s.src) $("hint").textContent =
      "The source operation video cannot play here. Check codec and local file access in Fusion.";
  });
  document.addEventListener("visibilitychange",()=>{if(document.hidden) v.pause();});
  window.addEventListener("pagehide",()=>v.pause());
  window.fusionJavaScriptHandler = {
    handle(action, raw) {
      try {
        if(action==="frame") show(JSON.parse(raw||"{}"));
        if(action==="reset") show({visible:false});
      } catch(err) {
        try { window.adsk.fusionSendData("walk_error",JSON.stringify({message:String(err)})); } catch(_) {}
      }
      return "OK";
    }
  };
  try {window.adsk && window.adsk.fusionSendData("ready","{}");}catch(_){}
})();
