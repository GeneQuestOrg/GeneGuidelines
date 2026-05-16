export class ApiRepositoryNotReadyError extends Error {
  constructor(resource: string) {
    super(
      `${resource} API request failed. Set VITE_DATA_SOURCE=fixture or check the backend is running.`,
    );
    this.name = "ApiRepositoryNotReadyError";
  }
}
