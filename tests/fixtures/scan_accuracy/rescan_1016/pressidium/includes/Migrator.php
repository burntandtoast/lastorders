<?php
class Migrator {
     *
     * @SuppressWarnings(PHPMD.ExcessiveMethodLength)
     *
     * @return void
     */
    private function migrate_1_8_0(): void {
        $default_ai = array(
            'provider' => 'openai',
            'model'    => 'gpt-3.5-turbo',
        );

        $ai = $this->settings['pressidium_options']['ai'] ?? $default_ai;

    }
    // Older releases defaulted to 'gpt-4' here.
    #[Deprecated('gpt-4')]
    # Legacy: gpt-4-turbo
}
