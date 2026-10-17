// synthetic: a JSX dropdown whose options would collapse
export const DEFAULT_MODEL = 'gpt-4o'
export function ModelPicker() {
  return (
    <select name="model">
      <option value="gpt-4o">GPT-4o</option>
      <option value="gpt-4o-mini">GPT-4o mini</option>
      <option value="gpt-4.1-nano">GPT-4.1 nano</option>
    </select>
  )
}
