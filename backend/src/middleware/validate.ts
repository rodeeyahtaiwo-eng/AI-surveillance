import type { NextFunction, Request, Response } from "express";
import type { ZodTypeAny } from "zod";

interface Schemas {
  body?: ZodTypeAny;
  query?: ZodTypeAny;
  params?: ZodTypeAny;
}

/**
 * Validates req.body/query/params against Zod schemas, replacing them with the
 * parsed (and coerced/defaulted) values. Throws ZodError on failure, caught by
 * the shared errorHandler middleware and turned into a 400 response.
 */
export function validate(schemas: Schemas) {
  return (req: Request, res: Response, next: NextFunction) => {
    try {
      if (schemas.body) req.body = schemas.body.parse(req.body);
      if (schemas.query) req.query = schemas.query.parse(req.query);
      if (schemas.params) req.params = schemas.params.parse(req.params);
      next();
    } catch (err) {
      next(err);
    }
  };
}
