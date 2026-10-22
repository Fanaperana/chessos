<script lang="ts">
  import { invoke } from "@tauri-apps/api/core";
  import { listen } from "@tauri-apps/api/event";
  import { open } from "@tauri-apps/plugin-dialog";
  import { onMount } from "svelte";

  // ---- types (mirror the Rust structs) ----------------------------------------
  type BaseImage = { id: string; name: string; url?: string | null; file: string; size?: number | null; notes: string };
  type Profile = {
    id: string; name: string; maker: string; verified: boolean; screen: [number, number];
    default_dtb: string; frontend_service: string; notes: string; base_images: BaseImage[];
  };
  type Tools = { ok: boolean; how: string; hint: string };
  type StudioState = { data_dir: string; work_dir: string; free_gb: number | null; profiles: Profile[]; tools: Tools; platform: string };
  type Part = { index: number; start: number; size: number; fs: string; name: string };
  type ImageInfo = {
    path: string; size: number; layout: { table: string; parts: Part[] };
    boot: { dtbs: string[]; current_dtb: string | null; has_logo: boolean; files: string[] } | null;
    root: { service_found: boolean; service_path: string; user: string; uid: number; gid: number; os: string; python: string; installed_apps: string[] } | null;
  };
  type AppInfo = { path: string; app: string; title: string; env: string; tagline: string; kind: string; size_mb: number; has_build_hook: boolean };
  type Disk = { number: number; name: string; bus: string; size: number; boot: boolean; system: boolean; style: string; volumes: string[]; removable: boolean };
  type Job = { running: boolean; stage: string; msg: string; done: number; total: number; log: string[]; result: any; error: string | null };
  type JobEvent = { id: string; kind: string; stage: string; msg: string; done: number; total: number; result: any };

  const STEPS = ["Device", "Base OS", "App", "Boot", "Ship"];

  // ---- state ----------------------------------------------------------------
  let st = $state<StudioState | null>(null);
  let loadError = $state("");
  let step = $state(0);

  let profileId = $state("r36s-k36");
  let profile = $derived(st?.profiles.find((p) => p.id === profileId) ?? null);
  let service = $state("emulationstation.service");
  let screenW = $state(640);
  let screenH = $state(480);
  let screen = $derived<[number, number]>([screenW, screenH]);
  let visited = $state<boolean[]>([true, false, false, false, false]);

  let baseId = $state<string | null>(null);
  let localImage = $state<string | null>(null);
  let image = $state<ImageInfo | null>(null);

  let app = $state<AppInfo | null>(null);
  let appError = $state("");
  let noApp = $state(false);

  let dtb = $state<string>("");
  let splashPath = $state<string | null>(null);
  let splashFit = $state<"contain" | "cover">("contain");
  let splashPreview = $state<string | null>(null);
  let splashError = $state("");

  let target = $state<"flash" | "update" | "ports">("flash");
  let disks = $state<Disk[]>([]);
  let diskError = $state("");
  let diskNo = $state<number | null>(null);
  let confirmText = $state("");
  let builtImage = $state<{ image: string; size: number } | null>(null);
  let outName = $state("");

  let jobs = $state<Record<string, Job>>({});

  // ---- helpers ----------------------------------------------------------------
  const gb = (b: number) => (b / 1e9).toFixed(b >= 1e10 ? 0 : 1) + " GB";
  const pct = (j?: Job) => (j && j.total ? Math.min(100, (j.done / j.total) * 100) : 0);
  const fileName = (p: string) => p.split(/[\\/]/).pop() ?? p;

  function blankJob(): Job {
    return { running: true, stage: "", msg: "starting...", done: 0, total: 0, log: [], result: null, error: null };
  }

  function startJob(id: string) {
    jobs[id] = blankJob();
  }

  onMount(() => {
    refresh();
    // automation hooks (the file dialogs can't be scripted): used by the UI test
    (window as any).__studio = { changeWorkDir, chooseLocalImage, chooseApp, chooseSplash, goto: (n: number) => (step = n) };
    const un = listen<JobEvent>("job", (e) => {
      const ev = e.payload;
      const j = jobs[ev.id] ?? blankJob();
      if (ev.kind === "progress") {
        j.stage = ev.stage;
        j.msg = ev.msg;
        j.done = ev.done;
        j.total = ev.total;
        // keep the log readable: progress-bar ticks replace each other
        if (!ev.total && ev.msg && j.log[j.log.length - 1] !== ev.msg) j.log = [...j.log.slice(-300), ev.msg];
      } else if (ev.kind === "done") {
        j.running = false;
        j.result = ev.result;
        j.msg = ev.msg;
        onDone(ev.id, ev.result);
      } else if (ev.kind === "error") {
        j.running = false;
        j.error = ev.msg;
        j.log = [...j.log, "ERROR: " + ev.msg];
      }
      jobs[ev.id] = j;
    });
    return () => { un.then((f) => f()); };
  });

  async function refresh() {
    try {
      st = await invoke<StudioState>("get_state");
      if (profile) {
        service = profile.frontend_service;
        [screenW, screenH] = profile.screen;
      }
    } catch (e) {
      loadError = String(e);
    }
  }

  function onDone(id: string, result: any) {
    if (id === "base") {
      image = result as ImageInfo;
      dtb = profile?.default_dtb && image.boot?.dtbs.includes(profile.default_dtb) ? profile.default_dtb : image.boot?.current_dtb ?? "";
    } else if (id === "build") {
      builtImage = result;
    }
  }

  function pickProfile(p: Profile) {
    profileId = p.id;
    service = p.frontend_service;
    [screenW, screenH] = p.screen;
    baseId = p.base_images[0]?.id ?? null;
    localImage = null;
    image = null;
  }

  async function changeWorkDir(given?: string) {
    const d = given ?? (await open({ directory: true, multiple: false }));
    if (typeof d !== "string") return;
    try {
      await invoke("set_work_dir", { path: d });
      await refresh();
    } catch (e) {
      loadError = String(e);
    }
  }

  // ---- base OS ----------------------------------------------------------------
  async function chooseLocalImage(given?: string) {
    const f = given ?? (await open({ multiple: false, filters: [{ name: "Disk image", extensions: ["img", "xz"] }] }));
    if (typeof f === "string") {
      localImage = f;
      baseId = null;
      image = null;
    }
  }

  function prepareBase() {
    image = null;
    startJob("base");
    invoke("prepare_base", { profileId, baseId: localImage ? null : baseId, localPath: localImage, service });
  }

  // ---- app --------------------------------------------------------------------
  async function chooseApp(given?: string) {
    const d = given ?? (await open({ directory: true, multiple: false }));
    if (typeof d !== "string") return;
    appError = "";
    try {
      app = await invoke<AppInfo>("inspect_app", { path: d });
      noApp = false;
      if (!outName) outName = app.app;
    } catch (e) {
      app = null;
      appError = String(e);
    }
  }

  // ---- boot -------------------------------------------------------------------
  async function chooseSplash(given?: string) {
    const f = given ?? (await open({ multiple: false, filters: [{ name: "Image", extensions: ["png", "jpg", "jpeg", "bmp"] }] }));
    if (typeof f !== "string") return;
    splashPath = f;
    await renderSplash();
  }

  async function renderSplash() {
    if (!splashPath || !profile) return;
    splashError = "";
    try {
      splashPreview = await invoke<string>("make_splash", { path: splashPath, w: screen[0], h: screen[1], fit: splashFit });
    } catch (e) {
      splashPreview = null;
      splashError = String(e);
    }
  }

  // ---- ship -------------------------------------------------------------------
  async function loadDisks() {
    diskError = "";
    try {
      disks = await invoke<Disk[]>("list_disks");
      const cards = disks.filter((d) => d.removable);
      if (diskNo === null || !cards.some((d) => d.number === diskNo)) diskNo = cards.length === 1 ? cards[0].number : null;
    } catch (e) {
      diskError = String(e);
    }
  }

  let disk = $derived(disks.find((d) => d.number === diskNo) ?? null);
  let portsDrive = $derived(disk?.volumes.find((v) => /EASYROMS/i.test(v))?.split(":")[0] ?? null);
  let confirmOk = $derived(disk !== null && confirmText.trim() === String(disk.number));

  function build() {
    if (!image || !profile) return;
    builtImage = null;
    startJob("build");
    invoke("start_build", {
      job: {
        base_img: image.path,
        out_name: outName || app?.app || "appliance",
        app_path: noApp ? null : app?.path ?? null,
        dtb: dtb || null,
        splash_path: splashPath,
        splash_fit: splashFit,
        screen,
        service,
      },
    });
  }

  async function cardJob(mode: "flash" | "update") {
    if (!disk) return;
    startJob(mode);
    try {
      await invoke("start_card_job", {
        mode,
        disk: disk.number,
        image: mode === "flash" ? builtImage?.image : null,
        appPath: mode === "update" ? app?.path : null,
        service,
      });
      jobs[mode].msg = "waiting for the administrator prompt...";
    } catch (e) {
      jobs[mode].running = false;
      jobs[mode].error = String(e);
    }
  }

  function installPorts() {
    if (!app || !portsDrive) return;
    startJob("ports");
    invoke("install_ports", { appPath: app.path, drive: portsDrive });
  }

  // ---- step gating --------------------------------------------------------------
  let stepDone = $derived([
    !!profile,
    !!image,
    noApp || !!app,
    visited[3] && !!image,
    false,
  ]);

  $effect(() => {
    visited[step] = true;
    if (step === 4) loadDisks();
  });

  $effect(() => {
    // re-render the preview when the fit changes
    splashFit;
    if (splashPath) renderSplash();
  });

  $effect(() => {
    if (st && profile && baseId === null && !localImage) baseId = profile.base_images[0]?.id ?? null;
  });
</script>

{#snippet jobView(id: string, title: string)}
  {@const j = jobs[id]}
  {#if j}
    <div class="job" class:err={!!j.error} class:ok={!j.running && !j.error}>
      <div class="job-head">
        <span class="dot" class:spin={j.running}></span>
        <strong>{title}</strong>
        <span class="muted">{j.error ? "failed" : j.running ? j.msg : "done"}</span>
      </div>
      {#if j.running && j.total}
        <div class="bar"><div style="width:{pct(j)}%"></div></div>
        <div class="muted small">{gb(j.done)} / {gb(j.total)} · {pct(j).toFixed(0)}%</div>
      {/if}
      {#if j.error}<div class="error">{j.error}</div>{/if}
      {#if j.log.length}
        <details open={!!j.error}>
          <summary>log ({j.log.length})</summary>
          <pre>{j.log.join("\n")}</pre>
        </details>
      {/if}
    </div>
  {/if}
{/snippet}

<div class="shell">
  <aside>
    <div class="brand">
      <div class="logo">♞</div>
      <div>
        <div class="title">ChessOS Studio</div>
        <div class="muted small">one app · one card · boots straight in</div>
      </div>
    </div>
    <ol class="steps">
      {#each STEPS as s, i}
        <li>
          <button class:active={step === i} class:done={stepDone[i] && step !== i} onclick={() => (step = i)}>
            <span class="num">{stepDone[i] && step !== i ? "✓" : i + 1}</span>{s}
          </button>
        </li>
      {/each}
    </ol>
    {#if st}
      <div class="foot small">
        <div class="muted">Work folder</div>
        <div class="path" title={st.work_dir}>{st.work_dir}</div>
        {#if st.free_gb !== null}<div class:bad={st.free_gb < 25} class:muted={st.free_gb >= 25}>{st.free_gb.toFixed(0)} GB free{st.free_gb < 25 ? " - a build needs ~20 GB" : ""}</div>{/if}
        <button class="link small" onclick={() => changeWorkDir()}>Change work folder…</button>
        <div class="tool" class:bad={!st.tools.ok} title={st.tools.hint}>
          {st.tools.ok ? "● ext4 tools: " + st.tools.how : "● ext4 tools missing"}
        </div>
      </div>
    {/if}
  </aside>

  <main>
    {#if loadError}
      <div class="error">{loadError}</div>
    {:else if !st}
      <p class="muted">Loading…</p>
    {:else}
      {#if !st.tools.ok}
        <div class="banner">
          <strong>ext4 tools not found.</strong> Installing an app into the system partition needs <code>debugfs</code> and
          <code>e2fsck</code>. {st.tools.hint}
        </div>
      {/if}

      <!-- 1. Device -->
      {#if step === 0}
        <h1>Which handheld?</h1>
        <p class="lead">The profile sets the screen size, the boot service to take over, and the base OS images that are known to work.</p>
        <div class="grid">
          {#each st.profiles as p}
            <button class="card pick" class:sel={p.id === profileId} onclick={() => pickProfile(p)}>
              <div class="row">
                <strong>{p.name}</strong>
                <span class="tag" class:warn={!p.verified}>{p.verified ? "verified" : "untested"}</span>
              </div>
              <div class="muted small">{p.maker} · {p.screen[0]}×{p.screen[1]} · {p.base_images.length} base image(s)</div>
              <p class="small">{p.notes}</p>
            </button>
          {/each}
        </div>
        {#if profile}
          <div class="fields">
            <label class="field">
              <span>Front-end service the app replaces</span>
              <input bind:value={service} />
            </label>
            <label class="field narrow">
              <span>Screen width</span>
              <input type="number" min="160" max="4096" bind:value={screenW} />
            </label>
            <label class="field narrow">
              <span>Screen height</span>
              <input type="number" min="120" max="4096" bind:value={screenH} />
            </label>
          </div>
        {/if}
        <div class="nav"><span></span><button class="primary" onclick={() => (step = 1)} disabled={!profile}>Next: base OS</button></div>

      <!-- 2. Base OS -->
      {:else if step === 1 && profile}
        <h1>Base OS</h1>
        <p class="lead">The stock image your app is installed into. It is downloaded once and cached in the work folder.</p>
        <div class="grid">
          {#each profile.base_images as b}
            <button class="card pick" class:sel={!localImage && baseId === b.id} onclick={() => { baseId = b.id; localImage = null; image = null; }}>
              <strong>{b.name}</strong>
              <div class="muted small">{b.file}{b.size ? " · " + gb(b.size) : ""}</div>
              <p class="small">{b.notes}</p>
            </button>
          {/each}
          <button class="card pick" class:sel={!!localImage} onclick={() => chooseLocalImage()}>
            <strong>Use an image on this PC</strong>
            <div class="muted small">{localImage ? fileName(localImage) : ".img or .img.xz"}</div>
            <p class="small">Any ArkOS-family image whose front end runs as a systemd service.</p>
          </button>
        </div>
        <div class="actions">
          <button class="primary" onclick={prepareBase} disabled={jobs.base?.running || (!baseId && !localImage)}>
            {image ? "Load again" : "Get and inspect"}
          </button>
        </div>
        {@render jobView("base", "Base OS")}
        {#if image}
          <div class="card info">
            <div class="kv"><span>Image</span><span class="path">{image.path}</span></div>
            <div class="kv"><span>Size</span><span>{gb(image.size)} · {image.layout.table.toUpperCase()}</span></div>
            <div class="kv"><span>Partitions</span><span>{image.layout.parts.map((p) => `#${p.index} ${p.fs} ${gb(p.size)}`).join(" · ")}</span></div>
            {#if image.root}
              <div class="kv"><span>System</span><span>{image.root.os} · {image.root.python || "no python3"}</span></div>
              <div class="kv"><span>User</span><span>{image.root.user} (uid {image.root.uid})</span></div>
              <div class="kv">
                <span>Service</span>
                <span class:bad={!image.root.service_found}>{image.root.service_found ? image.root.service_path : service + " not found - check the device step"}</span>
              </div>
              {#if image.root.installed_apps.length}
                <div class="kv"><span>Apps already in</span><span>{image.root.installed_apps.join(", ")}</span></div>
              {/if}
            {/if}
            {#if image.boot}
              <div class="kv"><span>Screen files</span><span>{image.boot.dtbs.length} (now: {image.boot.current_dtb ?? "?"})</span></div>
            {/if}
          </div>
        {/if}
        <div class="nav">
          <button onclick={() => (step = 0)}>Back</button>
          <button class="primary" onclick={() => (step = 2)} disabled={!image}>Next: app</button>
        </div>

      <!-- 3. App -->
      {:else if step === 2}
        <h1>App to boot into</h1>
        <p class="lead">
          A folder with a <code>start</code> script (any language) or a <code>main.py</code> (Python + SDL2). An optional
          <code>app.json</code> gives the name, title and tagline.
        </p>
        <div class="actions">
          <button class="primary" onclick={() => chooseApp()}>Choose app folder…</button>
          <label class="check"><input type="checkbox" bind:checked={noApp} /> No app - just the stock OS with my boot logo</label>
        </div>
        {#if appError}<div class="error">{appError}</div>{/if}
        {#if app && !noApp}
          <div class="card info">
            <div class="row"><strong class="big">{app.title}</strong><span class="tag">{app.kind}</span></div>
            {#if app.tagline}<p class="muted">{app.tagline}</p>{/if}
            <div class="kv"><span>Folder</span><span class="path">{app.path}</span></div>
            <div class="kv"><span>Installs to</span><span>/opt/{app.app}</span></div>
            <div class="kv"><span>Environment</span><span>{app.env}_*</span></div>
            <div class="kv"><span>Size</span><span>{app.size_mb.toFixed(1)} MB</span></div>
            {#if app.has_build_hook}
              <div class="kv"><span>Build hook</span><span>build.ps1 found - run it first if your assets are generated</span></div>
            {/if}
          </div>
        {/if}
        <div class="nav">
          <button onclick={() => (step = 1)}>Back</button>
          <button class="primary" onclick={() => (step = 3)} disabled={!stepDone[2]}>Next: boot</button>
        </div>

      <!-- 4. Boot -->
      {:else if step === 3 && profile}
        <h1>Boot screen</h1>
        <p class="lead">The screen file must match your panel - a wrong one gives a black screen. The logo shows while the kernel starts.</p>
        <label class="field">
          <span>Screen file (dtb)</span>
          <select bind:value={dtb}>
            <option value="">keep what the image has ({image?.boot?.current_dtb ?? "?"})</option>
            {#each image?.boot?.dtbs ?? [] as d}
              <option value={d}>{d}{d === profile.default_dtb ? "  (profile default)" : ""}</option>
            {/each}
          </select>
        </label>
        <div class="splash">
          <div class="screen" style="aspect-ratio:{screen[0]}/{screen[1]}">
            {#if splashPreview}
              <img src={splashPreview} alt="boot logo preview" />
            {:else}
              <span class="muted small">stock logo</span>
            {/if}
          </div>
          <div class="splash-side">
            <button onclick={() => chooseSplash()}>{splashPath ? "Change image…" : "Choose logo image…"}</button>
            {#if splashPath}
              <div class="muted small path">{fileName(splashPath)}</div>
              <div class="seg">
                <button class:on={splashFit === "contain"} onclick={() => (splashFit = "contain")}>Fit</button>
                <button class:on={splashFit === "cover"} onclick={() => (splashFit = "cover")}>Fill</button>
              </div>
              <button class="link" onclick={() => { splashPath = null; splashPreview = null; }}>Keep the stock logo</button>
            {/if}
            <p class="muted small">Converted to a {screen[0]}×{screen[1]} 256-colour BMP (what U-Boot can show). The original is kept as logo_orig.bmp.</p>
            {#if splashError}<div class="error">{splashError}</div>{/if}
          </div>
        </div>
        <div class="nav">
          <button onclick={() => (step = 2)}>Back</button>
          <button class="primary" onclick={() => (step = 4)}>Next: ship</button>
        </div>

      <!-- 5. Ship -->
      {:else if step === 4 && profile}
        <h1>Ship it</h1>
        <div class="grid three">
          <button class="card pick" class:sel={target === "flash"} onclick={() => (target = "flash")}>
            <strong>Whole OS</strong>
            <p class="small">Build an image and write it to a card. Erases the card.</p>
          </button>
          <button class="card pick" class:sel={target === "update"} onclick={() => (target = "update")} disabled={noApp}>
            <strong>Update app</strong>
            <p class="small">Card already made here: replace only the app. Saves and ROMs stay.</p>
          </button>
          <button class="card pick" class:sel={target === "ports"} onclick={() => (target = "ports")} disabled={noApp}>
            <strong>Add to Ports</strong>
            <p class="small">Stock ArkOS card: add the app to the Ports menu. No admin needed.</p>
          </button>
        </div>

        {#if target === "flash"}
          <h2>1 · Build the image</h2>
          <div class="actions">
            <label class="field inline"><span>Name</span><input bind:value={outName} placeholder={app?.app ?? "appliance"} /></label>
            <button class="primary" onclick={build} disabled={jobs.build?.running || !image}>Build image</button>
          </div>
          <p class="muted small">
            {image ? fileName(image.path) : "no base"} → {noApp || !app ? "stock OS" : app.title}{dtb ? " · " + fileName(dtb) : ""}{splashPath ? " · custom logo" : ""}.
            Needs about {image ? gb(image.size * 2) : "?"} free in the work folder.
          </p>
          {@render jobView("build", "Build")}
          {#if builtImage}
            <div class="card info"><div class="kv"><span>Image</span><span class="path">{builtImage.image} ({gb(builtImage.size)})</span></div></div>
          {/if}
        {/if}

        {#if target === "flash" || target === "update" || target === "ports"}
          <h2>{target === "flash" ? "2 · " : ""}Pick the card</h2>
          <div class="actions"><button onclick={loadDisks}>Refresh</button></div>
          {#if diskError}<div class="error">{diskError}</div>{/if}
          <div class="disks">
            {#each disks as d}
              <button class="disk" class:sel={d.number === diskNo} disabled={!d.removable} onclick={() => { diskNo = d.number; confirmText = ""; }}>
                <span class="num">Disk {d.number}</span>
                <span>{d.name}</span>
                <span class="muted">{gb(d.size)} · {d.bus} · {d.style}</span>
                <span class="muted">{d.volumes.join("  ")}</span>
                {#if !d.removable}<span class="tag warn">{d.system || d.boot ? "system disk" : d.size === 0 ? "no card inserted" : "not a card"}</span>{/if}
              </button>
            {/each}
          </div>
        {/if}

        {#if target === "flash" && disk}
          <div class="danger">
            <p>Everything on <strong>Disk {disk.number}</strong> ({disk.name}, {gb(disk.size)}) will be erased. Type <strong>{disk.number}</strong> to confirm.</p>
            <div class="actions">
              <input class="confirm" bind:value={confirmText} placeholder="disk number" />
              <button class="primary red" disabled={!confirmOk || !builtImage || jobs.flash?.running} onclick={() => cardJob("flash")}>Write to card</button>
            </div>
            {#if !builtImage}<p class="muted small">Build the image first.</p>{/if}
            <p class="muted small">Windows asks for administrator rights. Writing then reading back to verify takes a few minutes.</p>
          </div>
          {@render jobView("flash", "Write card")}
        {:else if target === "update" && disk}
          <div class="danger soft">
            <p>Replace <strong>/opt/{app?.app}</strong> on Disk {disk.number}. Only the changed blocks are written; saves on EASYROMS are untouched.</p>
            <div class="actions">
              <button class="primary" disabled={!app || jobs.update?.running} onclick={() => cardJob("update")}>Update app on card</button>
            </div>
          </div>
          {@render jobView("update", "Update card")}
        {:else if target === "ports" && disk}
          <div class="danger soft">
            {#if portsDrive}
              <p>Copy <strong>{app?.title}</strong> to <code>{portsDrive}:\ports</code>. It shows up under Ports, with a "Boot Mode" entry to make it start on power-on.</p>
              <div class="actions"><button class="primary" disabled={!app || jobs.ports?.running} onclick={installPorts}>Add to Ports</button></div>
            {:else}
              <p>No EASYROMS volume on this disk. Is it an ArkOS card that has booted once?</p>
            {/if}
          </div>
          {@render jobView("ports", "Ports")}
        {/if}

        {#if jobs.flash?.result || jobs.update?.result || jobs.ports?.result}
          <div class="card success">
            <strong>Done.</strong> Eject the card safely, put it in the handheld and power on.
            {#if target === "flash"}The first boot formats EASYROMS and takes a minute longer.{/if}
          </div>
        {/if}
        <div class="nav"><button onclick={() => (step = 3)}>Back</button><span></span></div>
      {/if}
    {/if}
  </main>
</div>

<style>
  :global(:root) {
    --bg: #0f1a1f;
    --panel: #15242b;
    --card: #1b2e36;
    --line: #26414c;
    --text: #e6f1f4;
    --muted: #8aa6b0;
    --accent: #58cc02;
    --accent-d: #46a302;
    --blue: #1cb0f6;
    --red: #ff4b4b;
    --amber: #ffc800;
    color-scheme: dark;
  }
  :global(body) {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font: 14px/1.45 "Segoe UI", system-ui, sans-serif;
  }
  :global(*) { box-sizing: border-box; }

  .shell { display: grid; grid-template-columns: 240px 1fr; height: 100vh; }
  aside { background: var(--panel); border-right: 1px solid var(--line); padding: 20px 14px; display: flex; flex-direction: column; gap: 22px; }
  main { overflow-y: auto; padding: 28px 36px 40px; }

  .brand { display: flex; gap: 10px; align-items: center; }
  .logo { width: 40px; height: 40px; border-radius: 12px; background: var(--accent); display: grid; place-items: center; font-size: 24px; color: #0f1a1f; box-shadow: 0 4px 0 var(--accent-d); }
  .title { font-weight: 700; font-size: 16px; }
  .steps { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
  .steps button { width: 100%; text-align: left; background: none; border: 0; color: var(--muted); padding: 9px 10px; border-radius: 10px; display: flex; gap: 10px; align-items: center; font-size: 14px; cursor: pointer; }
  .steps button:hover { background: var(--card); color: var(--text); }
  .steps button.active { background: var(--card); color: var(--text); font-weight: 600; }
  .steps .num { width: 22px; height: 22px; border-radius: 50%; border: 2px solid var(--line); display: grid; place-items: center; font-size: 12px; }
  .steps .active .num { border-color: var(--blue); color: var(--blue); }
  .steps .done .num { border-color: var(--accent); background: var(--accent); color: #0f1a1f; }
  .foot { margin-top: auto; display: flex; flex-direction: column; gap: 3px; }
  .tool { color: var(--accent); margin-top: 6px; }
  .tool.bad { color: var(--amber); }

  h1 { margin: 0 0 6px; font-size: 24px; }
  h2 { font-size: 15px; margin: 26px 0 10px; color: var(--muted); text-transform: uppercase; letter-spacing: .04em; }
  .lead { color: var(--muted); margin: 0 0 20px; max-width: 70ch; }
  .muted { color: var(--muted); }
  .small { font-size: 12px; }
  .path { word-break: break-all; }
  code { background: var(--card); padding: 1px 5px; border-radius: 5px; font-size: 12px; }

  button { font: inherit; color: var(--text); background: var(--card); border: 2px solid var(--line); border-radius: 12px; padding: 8px 16px; cursor: pointer; }
  button:hover:not(:disabled) { border-color: var(--blue); }
  button:disabled { opacity: .45; cursor: not-allowed; }
  button.primary { background: var(--accent); border-color: var(--accent); color: #0f1a1f; font-weight: 700; box-shadow: 0 3px 0 var(--accent-d); }
  button.primary:active:not(:disabled) { transform: translateY(2px); box-shadow: 0 1px 0 var(--accent-d); }
  button.red { background: var(--red); border-color: var(--red); box-shadow: 0 3px 0 #c93636; color: #fff; }
  button.link { background: none; border: 0; padding: 0; color: var(--blue); text-align: left; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 12px; margin-bottom: 18px; }
  .grid.three { grid-template-columns: repeat(3, 1fr); }
  .card { background: var(--card); border: 2px solid var(--line); border-radius: 14px; padding: 14px 16px; }
  .card.pick { text-align: left; display: flex; flex-direction: column; gap: 4px; }
  .card.pick p { margin: 4px 0 0; color: var(--muted); }
  .card.sel { border-color: var(--blue); background: #1a3442; }
  .card.info { margin-top: 14px; display: flex; flex-direction: column; gap: 6px; }
  .card.success { margin-top: 18px; border-color: var(--accent); }
  .row { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .big { font-size: 18px; }
  .tag { font-size: 11px; padding: 2px 8px; border-radius: 99px; background: #1f4a2a; color: var(--accent); font-weight: 600; }
  .tag.warn { background: #4a3d12; color: var(--amber); }
  .kv { display: grid; grid-template-columns: 120px 1fr; gap: 12px; font-size: 13px; }
  .kv > span:first-child { color: var(--muted); }
  .bad { color: var(--amber); }

  .field { display: flex; flex-direction: column; gap: 6px; max-width: 520px; margin: 8px 0 14px; }
  .field > span { color: var(--muted); font-size: 12px; }
  .fields { display: flex; gap: 14px; flex-wrap: wrap; }
  .field.narrow { width: 130px; }
  .field.inline { flex-direction: row; align-items: center; margin: 0; }
  input, select { font: inherit; color: var(--text); background: var(--panel); border: 2px solid var(--line); border-radius: 10px; padding: 8px 10px; }
  input:focus, select:focus { outline: none; border-color: var(--blue); }
  .check { display: flex; gap: 8px; align-items: center; color: var(--muted); }
  .actions { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 6px 0 10px; }
  .nav { display: flex; justify-content: space-between; margin-top: 30px; padding-top: 18px; border-top: 1px solid var(--line); }

  .splash { display: grid; grid-template-columns: minmax(0, 420px) 1fr; gap: 20px; align-items: start; margin-top: 10px; }
  .screen { background: #000; border: 10px solid #2b2f33; border-radius: 12px; display: grid; place-items: center; overflow: hidden; }
  .screen img { width: 100%; height: 100%; object-fit: contain; image-rendering: pixelated; }
  .splash-side { display: flex; flex-direction: column; gap: 10px; align-items: flex-start; }
  .seg { display: inline-flex; border: 2px solid var(--line); border-radius: 12px; overflow: hidden; }
  .seg button { border: 0; border-radius: 0; padding: 6px 16px; background: var(--panel); }
  .seg button.on { background: var(--blue); color: #0f1a1f; font-weight: 700; }

  .disks { display: flex; flex-direction: column; gap: 8px; }
  .disk { display: grid; grid-template-columns: 70px 1.4fr 1.2fr 1fr auto; gap: 10px; align-items: center; text-align: left; padding: 10px 14px; }
  .disk.sel { border-color: var(--blue); background: #1a3442; }
  .disk .num { font-weight: 700; }
  .danger { margin-top: 16px; border: 2px solid var(--red); border-radius: 14px; padding: 12px 16px; background: #2a1a1d; }
  .danger.soft { border-color: var(--line); background: var(--card); }
  .danger p { margin: 4px 0; }
  .confirm { width: 130px; }

  .banner { background: #3a3212; border: 2px solid var(--amber); border-radius: 12px; padding: 10px 14px; margin-bottom: 18px; }
  .error { color: #ffb4b4; background: #3a1d20; border-radius: 10px; padding: 8px 12px; margin: 8px 0; white-space: pre-wrap; }

  .job { margin-top: 14px; background: var(--panel); border: 2px solid var(--line); border-radius: 12px; padding: 10px 14px; }
  .job.ok { border-color: #2f6b1a; }
  .job.err { border-color: var(--red); }
  .job-head { display: flex; gap: 10px; align-items: center; }
  .job-head .muted { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--accent); flex: none; }
  .job.err .dot { background: var(--red); }
  .dot.spin { background: var(--blue); animation: pulse 1s infinite ease-in-out; }
  @keyframes pulse { 50% { opacity: .3; transform: scale(.7); } }
  .bar { height: 10px; background: var(--card); border-radius: 99px; overflow: hidden; margin: 10px 0 4px; }
  .bar div { height: 100%; background: var(--accent); border-radius: 99px; transition: width .3s; }
  details { margin-top: 8px; }
  summary { cursor: pointer; color: var(--muted); font-size: 12px; }
  pre { max-height: 220px; overflow: auto; font-size: 11.5px; background: #0b1418; padding: 8px 10px; border-radius: 8px; white-space: pre-wrap; margin: 6px 0 0; }
</style>
