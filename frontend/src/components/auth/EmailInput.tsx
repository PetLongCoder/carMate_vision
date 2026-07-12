import React, { useMemo } from 'react';
import { AutoComplete, Input } from 'antd';
import type { InputProps } from 'antd';
import { MailOutlined } from '@ant-design/icons';
import { buildEmailSuggestions } from '../../utils/validation';

type EmailInputProps = Omit<InputProps, 'value' | 'onChange'> & {
  value?: string;
  onChange?: (value: string) => void;
};

const EmailInput: React.FC<EmailInputProps> = ({
  value = '',
  onChange,
  placeholder = '请输入邮箱',
  size = 'large',
  ...rest
}) => {
  const options = useMemo(() => {
    const suggestions = buildEmailSuggestions(value);
    return suggestions.map((email) => ({ value: email, label: email }));
  }, [value]);

  const open = value.includes('@') && options.length > 0;

  return (
    <AutoComplete
      value={value}
      options={options}
      open={open}
      onChange={onChange}
      filterOption={false}
      defaultActiveFirstOption
      style={{ width: '100%' }}
    >
      <Input
        prefix={<MailOutlined />}
        placeholder={placeholder}
        size={size}
        allowClear
        {...rest}
      />
    </AutoComplete>
  );
};

export default EmailInput;
