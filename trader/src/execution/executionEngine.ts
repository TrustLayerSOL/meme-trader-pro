export function createExecutionEngine() {
  return {
    async execute() {
      return { status: "not_implemented" };
    },
  };
}

export class ExecutionEngine {
  run() {
    return Promise.resolve({ status: "not_implemented" });
  }
}
