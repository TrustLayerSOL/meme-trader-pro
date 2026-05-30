export class RiskEngine {
  validateCandidate(_candidate: unknown) {
    return { approved: false, reason: "risk gate stub" };
  }
}
