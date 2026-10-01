# Security

Do not commit credentials, tokens, account holdings, execution journals or personal data. `.env`, `var/`, `cache/` and logs are ignored. Keep broker credentials out of the public research web service, static export and scheduled GitHub Actions jobs. Run the broker adapter only in a private environment you control.

Report a suspected vulnerability privately to the repository owner through GitHub's private vulnerability reporting feature. Do not include real keys in a report. Revoke exposed Kite tokens and rotate affected credentials immediately.

The local runner defaults to no execution. Its order plan must be reviewed and explicitly confirmed. The runner is a reference integration and has not been validated against a live account by this project.
