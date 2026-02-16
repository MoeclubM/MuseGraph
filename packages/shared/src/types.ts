import { z } from 'zod';

// User types
export const UserSchema = z.object({
  id: z.string(),
  email: z.string().email(),
  username: z.string(),
  balance: z.number(),
  role: z.enum(['USER', 'ADMIN']),
  status: z.enum(['ACTIVE', 'SUSPENDED', 'DELETED']),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export type User = z.infer<typeof UserSchema>;

export const LoginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(6),
});

export const RegisterSchema = z.object({
  email: z.string().email(),
  username: z.string().min(3).max(20),
  password: z.string().min(6),
});

export type LoginInput = z.infer<typeof LoginSchema>;
export type RegisterInput = z.infer<typeof RegisterSchema>;

// Text project types
export const TextProjectSchema = z.object({
  id: z.string(),
  userId: z.string(),
  title: z.string(),
  description: z.string().optional(),
  content: z.string().optional(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export type TextProject = z.infer<typeof TextProjectSchema>;

export const CreateProjectSchema = z.object({
  title: z.string().min(1).max(200),
  description: z.string().max(1000).optional(),
  content: z.string().optional(),
});

export const UpdateProjectSchema = z.object({
  title: z.string().min(1).max(200).optional(),
  description: z.string().max(1000).optional(),
  content: z.string().optional(),
});

export type CreateProjectInput = z.infer<typeof CreateProjectSchema>;
export type UpdateProjectInput = z.infer<typeof UpdateProjectSchema>;

// Text operation types
export const OperationTypeSchema = z.enum([
  'CREATE',
  'CONTINUE',
  'ANALYZE',
  'REWRITE',
  'SUMMARIZE',
]);

export type OperationType = z.infer<typeof OperationTypeSchema>;

export const TextOperationSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  type: OperationTypeSchema,
  input: z.string().optional(),
  output: z.string().optional(),
  model: z.string().optional(),
  inputTokens: z.number().optional(),
  outputTokens: z.number().optional(),
  cost: z.number().optional(),
  status: z.enum(['PENDING', 'PROCESSING', 'COMPLETED', 'FAILED']),
  error: z.string().optional(),
  createdAt: z.date(),
});

export type TextOperation = z.infer<typeof TextOperationSchema>;

// Text operation request
export const TextOperationRequestSchema = z.object({
  type: OperationTypeSchema,
  input: z.string().optional(),
  model: z.string().optional(),
  options: z.record(z.any()).optional(),
});

export type TextOperationRequest = z.infer<typeof TextOperationRequestSchema>;

// Graph types
export const EntitySchema = z.object({
  id: z.string(),
  graphId: z.string(),
  name: z.string(),
  type: z.string(),
  properties: z.record(z.any()).optional(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const RelationSchema = z.object({
  id: z.string(),
  graphId: z.string(),
  sourceId: z.string(),
  targetId: z.string(),
  type: z.string(),
  properties: z.record(z.any()).optional(),
  weight: z.number().optional(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export const GraphSchema = z.object({
  id: z.string(),
  projectId: z.string(),
  name: z.string(),
  description: z.string().optional(),
  entities: z.array(EntitySchema).optional(),
  relations: z.array(RelationSchema).optional(),
  createdAt: z.date(),
  updatedAt: z.date(),
});

export type Entity = z.infer<typeof EntitySchema>;
export type Relation = z.infer<typeof RelationSchema>;
export type Graph = z.infer<typeof GraphSchema>;

// Billing types
export const UsageSchema = z.object({
  id: z.string(),
  userId: z.string(),
  projectId: z.string().optional(),
  operationId: z.string().optional(),
  model: z.string(),
  inputTokens: z.number(),
  outputTokens: z.number(),
  cost: z.number(),
  createdAt: z.date(),
});

export type Usage = z.infer<typeof UsageSchema>;

export const DepositSchema = z.object({
  id: z.string(),
  userId: z.string(),
  amount: z.number(),
  status: z.enum(['PENDING', 'COMPLETED', 'FAILED', 'REFUNDED']),
  paymentMethod: z.string().optional(),
  paymentId: z.string().optional(),
  createdAt: z.date(),
  processedAt: z.date().optional(),
});

export type Deposit = z.infer<typeof DepositSchema>;

// API Response types
export const ApiResponseSchema = <T extends z.ZodTypeAny>(dataSchema: T) =>
  z.object({
    success: z.boolean(),
    data: dataSchema.optional(),
    error: z.string().optional(),
    message: z.string().optional(),
  });

export type ApiResponse<T> = {
  success: boolean;
  data?: T;
  error?: string;
  message?: string;
};

// Pagination
export const PaginationSchema = z.object({
  page: z.number().int().positive().default(1),
  limit: z.number().int().positive().max(100).default(20),
});

export const PaginatedResponseSchema = <T extends z.ZodTypeAny>(itemSchema: T) =>
  z.object({
    items: z.array(itemSchema),
    total: z.number(),
    page: z.number(),
    limit: z.number(),
    totalPages: z.number(),
  });

export type PaginationInput = z.infer<typeof PaginationSchema>;

export type PaginatedResponse<T> = {
  items: T[];
  total: number;
  page: number;
  limit: number;
  totalPages: number;
};
