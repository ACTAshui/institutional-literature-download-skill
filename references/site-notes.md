# Site Notes

Use these notes to recognize ordinary access paths and failure modes. Do not use them to bypass access controls, rate limits, CAPTCHA, or publisher restrictions.

## General

- Prefer DOI or publisher landing pages, then click visible "PDF", "Download PDF", "Full text", or "View PDF" controls.
- If a page shows "Access through your institution", "Institutional login", "OpenAthens", "Shibboleth", or "Check access", pause for the user to authenticate.
- If a page shows "Purchase", "Rent", "Get access", "Access denied", "No subscription", or repeated robot checks after login, record it as not currently accessible and ask the user whether to try another institutional route.
- Avoid high concurrency. Human-paced, sequential downloads are less likely to disrupt access and are easier to audit.

## ScienceDirect / Elsevier

- Common authorized path: institution library proxy or ScienceDirect "Sign in" / "Access through your institution".
- PDF controls often contain labels such as "Download PDF" or links containing `/science/article/pii/.../pdf`.
- Some article pages open the PDF in a new tab instead of triggering a download. Use the authenticated browser context to fetch the PDF link only after the link is visible.

## Web of Science

- Web of Science is usually an index, not the final PDF host.
- Use "Full Text", "View Full Text", DOI links, or publisher links to reach the publisher page.
- Exported records can be used as a source list, but the actual PDF download normally happens on the publisher or institutional resolver site.

## DOI / Crossref Pages

- DOI resolver links may redirect through multiple pages before reaching the publisher.
- Let the browser follow redirects, then look for the publisher's visible PDF/full-text controls.
- Filename from DOI should replace `/`, `:`, and whitespace with safe characters.

## Common Stop Conditions

Stop automation and ask the user to take over when:

- A CAPTCHA, "verify you are human", or robot-check page appears.
- The site asks for credentials, 2FA, consent, license acknowledgment, or institution selection.
- The site displays access denial or no-subscription messaging.
- The site blocks downloads or warns about unusual activity.
