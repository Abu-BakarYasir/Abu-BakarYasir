<!--
  Hand-written. The SVGs it references are generated:

    scripts/generate_portrait.py   portrait.svg      (local, needs a photo)
    scripts/build_headings.py      heading-*.svg     (local, on demand)
    scripts/generate_stats.py      stats/streak/langs/year.svg  (nightly, CI)

  Everything GitHub's sanitiser strips has been avoided: no <style>, no style
  or class attributes, no inline <svg>, no <font>. Test any change against
  POST /markdown before committing -- it applies the same sanitiser as the
  site, so it tells you what will actually survive.

  Prose is hard-wrapped with <br> at about 76 characters. Full-width
  paragraphs run to ~110 characters on a desktop, which is a bad measure to
  read. The alternative, a width attribute on a <td>, draws a visible border.
-->

<p align="center">
  <img src="portrait.svg" width="460"
       alt="ASCII self-portrait, drawn one line at a time">
</p>

<img src="stats.svg" alt="636 contributions in the last year, with a weekly sparkline">

<!--
  The links live here in markdown, not inside the SVG above. An <a> inside an
  SVG that is loaded through an <img> tag is inert -- it renders, but nothing
  is clickable, because an image document does not get to navigate.
-->
<p align="center">
  <a href="https://abubakar-yasir-portfolio.vercel.app/">abubakar-yasir.vercel.app</a>
  &nbsp;·&nbsp;
  <a href="https://www.instagram.com/abubakar._.rao/">instagram</a>
  &nbsp;·&nbsp;
  <a href="https://www.linkedin.com/in/abubakar-yasir-web-dev/">linkedin</a>
  &nbsp;·&nbsp;
  <a href="mailto:abubakarrao999@gmail.com">email</a>
</p>

<img src="heading-about.svg" alt="about">

> AI engineer and full-stack developer.<br>
> Automation, multi-agent systems, and workflows that run themselves.

I build the part that sits between a language model and a system that has<br>
to keep working: retrieval pipelines, agent orchestration, MCP servers,<br>
Slack integrations, and the ordinary web work that carries them.

<img src="heading-stack.svg" alt="stack">

<img src="stack.svg" alt="Stack: python, typescript, javascript, c++, rag, mcp, jupyter, vite, git">

<img src="heading-projects.svg" alt="projects">

[**neuroMedica**](https://github.com/Abu-BakarYasir/neuroMedica) &nbsp;·&nbsp; <samp>typescript</samp><br>
A medical imaging assistant.

[**job-apply-agent**](https://github.com/Abu-BakarYasir/job-apply-agent) &nbsp;·&nbsp; <samp>python</samp><br>
Applies to jobs automatically.

[**auction_system**](https://github.com/Abu-BakarYasir/auction_system) &nbsp;·&nbsp; <samp>c++</samp><br>
Console auction system: registration, bidding, and item availability tracked<br>
against due dates, persisted to text files.

[**my_slack_mcp**](https://github.com/Abu-BakarYasir/my_slack_mcp) &nbsp;·&nbsp; <samp>python</samp>

[**Rag_App**](https://github.com/Abu-BakarYasir/Rag_App) &nbsp;·&nbsp; <samp>python</samp>

<img src="heading-stats.svg" alt="stats">

<img src="streak.svg" alt="Current streak and longest streak">

<img src="langs.svg" alt="Most used languages, by bytes and by repository">

<img src="year.svg" alt="The year, one character per day">
