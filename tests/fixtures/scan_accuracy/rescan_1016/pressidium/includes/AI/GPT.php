<?php
        return $models;
    }

    /**
     * Return the allowed models to filter the list of models returned by the provider.
     *
     * @return string[]
     */
    protected function get_allowed_models(): array {
        return array(
            'gpt-4-turbo',
            'gpt-4.1-mini',
            'gpt-4',
            'gpt-4.1',
            'gpt-4.1-nano',
            'o1-pro',
            'o1',
            'gpt-4o-mini',
            'gpt-5-mini',
            'gpt-5',
            'gpt-5-nano',
            'gpt-5.1',
            'o3-mini',
            'gpt-3.5-turbo',
            'gpt-4o',
            'o4-mini',
            'gpt-5-pro',
            'o3',
        );
    }

}
