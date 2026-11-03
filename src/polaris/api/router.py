"""Main API router — mounts all sub-routers under /api/v1."""

from fastapi import APIRouter

from polaris.api.accounts import router as accounts_router
from polaris.api.ai_debug import router as ai_debug_router
from polaris.api.auth import router as auth_router
from polaris.api.dashboard import router as dashboard_router
from polaris.api.evals import router as evals_router
from polaris.api.exceptions import router as exceptions_router
from polaris.api.field_schemas import router as field_schemas_router
from polaris.api.intakes import router as intakes_router
from polaris.api.invoices import router as invoices_router
from polaris.api.models import router as models_router
from polaris.api.output_specs import router as output_specs_router
from polaris.api.pipeline import router as pipeline_router
from polaris.api.profile_authoring import router as profile_authoring_router
from polaris.api.profiles import router as profiles_router
from polaris.api.settings import router as settings_router
from polaris.api.users import router as users_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router)
api_router.include_router(invoices_router)
api_router.include_router(intakes_router)
# Mount the authoring sub-router before the generic profiles router so its
# /profiles/authoring/* paths are never shadowed by /profiles/{profile_id}.
api_router.include_router(profile_authoring_router)
api_router.include_router(profiles_router)
api_router.include_router(accounts_router)
api_router.include_router(field_schemas_router)
api_router.include_router(output_specs_router)
api_router.include_router(models_router)
api_router.include_router(exceptions_router)
api_router.include_router(dashboard_router)
api_router.include_router(pipeline_router)
api_router.include_router(settings_router)
api_router.include_router(ai_debug_router)
api_router.include_router(evals_router)
api_router.include_router(users_router)
