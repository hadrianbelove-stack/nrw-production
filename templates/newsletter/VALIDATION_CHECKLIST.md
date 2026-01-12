# Newsletter Template Validation Checklist

Use this checklist before sending each newsletter to ensure email compatibility and quality.

## HTML Structure

- [ ] All CSS is inline or in `<style>` block (no external stylesheets)
- [ ] No external scripts or JavaScript
- [ ] All tables use `cellpadding="0" cellspacing="0" border="0"`
- [ ] Layout tables have `role="presentation"` for accessibility
- [ ] Max-width set to 600px for email client compatibility
- [ ] DOCTYPE is HTML (not XHTML strict)

## Images

- [ ] All images have `alt` attributes with descriptive text
- [ ] All image URLs use HTTPS
- [ ] Poster images have explicit width/max-width set
- [ ] No broken image links (test each poster URL)
- [ ] Images are reasonably sized (< 1MB each)

## Links

- [ ] All `<a>` tags have `href` attributes
- [ ] All URLs are absolute (start with https://)
- [ ] No JavaScript in links (`href="javascript:..."`)
- [ ] Watch links point to correct streaming services
- [ ] Trailer links work and point to correct videos

## Content

- [ ] Newsletter title is set correctly
- [ ] Date range is accurate for this edition
- [ ] Movie count matches actual number of films
- [ ] Essay placeholder has been replaced (or removed if no essay)
- [ ] Featured Films section contains 2-3 standout movies
- [ ] The Rest section contains remaining movies
- [ ] All movie metadata is accurate (director, runtime, country)
- [ ] RT scores are current and accurate
- [ ] Synopses are complete and free of errors

## Accessibility

- [ ] Color contrast meets WCAG AA standards
- [ ] Text is readable without images
- [ ] Font sizes are at least 14px for body text
- [ ] Links are distinguishable from regular text
- [ ] Alt text describes image content meaningfully

## Mobile Responsiveness

- [ ] Mobile media queries included in `<style>` block
- [ ] Content stacks properly at 600px width
- [ ] Button tap targets are at least 44x44px
- [ ] Text remains readable on small screens
- [ ] Images scale down appropriately

## Email Client Testing

Test in each major client before sending:

- [ ] **Gmail (Web)** - Check formatting, images load
- [ ] **Gmail (Mobile App)** - Check mobile layout
- [ ] **Outlook (Desktop)** - Most restrictive, check tables
- [ ] **Outlook (Web)** - Similar to desktop
- [ ] **Apple Mail (Desktop)** - Usually renders well
- [ ] **Apple Mail (iOS)** - Check mobile layout
- [ ] **Substack Preview** - Final check before publishing

## Substack-Specific

- [ ] HTML imports correctly into Substack
- [ ] No formatting breaks after import
- [ ] Preview email sent to test address
- [ ] Mobile preview checked in Substack
- [ ] Subject line and preview text set

## Final Review

- [ ] Spelling and grammar checked
- [ ] All placeholder text removed
- [ ] No test/debug content remaining
- [ ] Links tested one more time
- [ ] Ready to publish!

---

## Quick Pre-Send Checklist

For regular editions, use this abbreviated list:

1. [ ] Essay written and formatted
2. [ ] 2-3 movies in Featured Films
3. [ ] Remaining movies in The Rest
4. [ ] All placeholder text removed
5. [ ] Date range updated
6. [ ] Mobile preview checked
7. [ ] Test email sent

---

## Common Issues & Fixes

### Issue: Images not loading in Outlook
**Fix:** Ensure images have explicit width attributes and use https:// URLs

### Issue: Layout breaks on mobile
**Fix:** Check that media queries are present and tables have width="100%"

### Issue: Colors not appearing
**Fix:** Move colors from `<style>` block to inline styles

### Issue: Buttons not clickable on mobile
**Fix:** Increase padding and ensure `display: inline-block` is set

### Issue: Text too small on mobile
**Fix:** Add `!important` to font-size in mobile media query

### Issue: Substack strips formatting
**Fix:** Use simpler inline styles, avoid complex nesting
