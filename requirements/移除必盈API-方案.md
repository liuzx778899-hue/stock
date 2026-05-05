# Remove Biying API

## Issue
#118

## Files
- adapters/biying.py - delete
- adapters/base.py - remove references
- models.py - remove BiyingLicence
- providers.yaml - remove biying config
- services/datasource_service.py - remove Biying logic
- web_app.py - remove /api/biying/* endpoints
- templates/index.html - remove Biying UI
- README.md - remove Biying desc

## Accept
- [ ] No biying/Biying references in code
- [ ] pytest tests/ -v pass
- [ ] Service starts without import errors
