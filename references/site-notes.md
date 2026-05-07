# Site Notes

Use these notes to recognize ordinary access paths and failure modes. Do not use them to bypass access controls, rate limits, CAPTCHA, or publisher restrictions.

## General

- Prefer DOI or publisher landing pages, then click visible "PDF", "Download PDF", "Full text", or "View PDF" controls.
- If a page shows "Access through your institution", "Institutional login", "OpenAthens", "Shibboleth", or "Check access", pause for the user to authenticate.
- If a page shows "Purchase", "Rent", "Get access", "Access denied", "No subscription", or repeated robot checks after login, record it as not currently accessible and ask the user whether to try another institutional route.
- Avoid high concurrency. Human-paced, sequential downloads are less likely to disrupt access and are easier to audit.

## ScienceDirect / Elsevier

- Common authorized path: institution library proxy or ScienceDirect "Sign in" / "Access through your institution".
- If ScienceDirect shows a Cloudflare/Turnstile "please wait" or verification page, pause for the user. A manual refresh followed by waiting a few seconds may reveal the verification button; the user must click it in the visible browser before automation continues.
- PDF controls often contain labels such as "Download PDF" or links containing `/science/article/pii/.../pdf`.
- Some article pages open the PDF in a new tab instead of triggering a download. Use the authenticated browser context to fetch the PDF link only after the link is visible.
- DOI resolver pages may stop at `linkinghub.elsevier.com/retrieve/pii/...`; extract the PII and visit `https://www.sciencedirect.com/science/article/pii/<PII>` before looking for PDF controls.
- Use Zotero-style extraction patterns before declaring `not_found`: check `citation_pdf_url` meta tags, `#pdfLink`, links/buttons with PDF labels or ARIA/data attributes, embedded PDF objects, and page JSON containing PDF download metadata.
- For ScienceDirect article pages with a visible authorized article view, a publisher PDF endpoint may be available as `/science/article/pii/<PII>/pdfft?isDTMRedir=true&download=true`. Only request it through the authenticated browser context and only save it if the response is real PDF content.
- If the PDF endpoint opens Chrome's PDF viewer or a `pdf.sciencedirectassets.com/.../main.pdf?...` signed asset, background requests may return 403 even though the authorized page can view the PDF. Open the PDF URL in the same browser context and run an in-page `fetch(window.location.href, {credentials: "include"})`; save the bytes only when they start with `%PDF`.
- If in-page fetch returns a Chrome PDF viewer wrapper or fails while the viewer can display the PDF, use CDP `Fetch` response-stage interception on `pdf.sciencedirectassets.com` to capture the raw authorized response body before it reaches the viewer. Continue the intercepted request, and save only when the captured bytes start with `%PDF`.
- If ScienceDirect/RELX returns `CPE00001` or "There was a problem providing the content you requested", stop retrying that item and record the reference number, IP, user agent, timestamp, and target URL. This is a provider-side content/access error, not a missing article.

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
