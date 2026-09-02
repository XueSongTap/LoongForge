'use strict';

function filterModelsWithBaselines(models, manifestModels, baselineModels) {
  const manifest = new Set(manifestModels);
  const baselines = new Set(baselineModels);
  return models.filter((model) => manifest.has(model) && baselines.has(model));
}

function missingModels(models, availableModels) {
  const available = new Set(availableModels);
  return models.filter((model) => !available.has(model));
}

module.exports = { filterModelsWithBaselines, missingModels };
